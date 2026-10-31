# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""System Readiness & Diagnostic Orchestration Engine."""

import asyncio
import time
from typing import Any

from bagel.diagnostics.probes.adb_probe import AdbDeviceProbe
from bagel.diagnostics.probes.base import BaseProbe
from bagel.diagnostics.probes.runtime_probe import (
    PythonRuntimeProbe,
)
from bagel.diagnostics.probes.toolchain_probe import ToolchainProbe
from bagel.diagnostics.schema import (
    DeviceInfo,
    ProbeAction,
    ProbeCategory,
    ProbeResult,
    ProbeStatus,
    SystemReadinessReport,
)
from bagel.toolchain import toolchain
from bagel.platform import platform
from third_party.mobile_use.utils.logger import get_logger

logger = get_logger(__name__)


class ReadinessEngine:
    """Central orchestration engine executing modular readiness probes."""

    _REPORT_CACHE_TTL_SECONDS = 2.0

    #: Deadline for one probe inside a report. The ADB probe shells out to
    #: ``adb`` without a deadline of its own, and a wedged ADB server would
    #: otherwise hang every surface that runs the report (``bagel doctor``,
    #: ``mobile_diagnose``). A probe that overruns is
    #: reported as a FAIL with the recovery steps instead.
    PROBE_TIMEOUT_SECONDS = 30.0

    def __init__(self):
        self._probes: dict[str, BaseProbe] = {}
        self._python_probe = PythonRuntimeProbe()
        self._toolchain_probe = ToolchainProbe()
        self._adb_probe = AdbDeviceProbe()
        self._report_cache: SystemReadinessReport | None = None
        self._report_cache_time = 0.0
        self._report_cache_generation = -1
        self._cache_generation = 0
        self._report_lock = asyncio.Lock()

        # Register default core probes in logical lifecycle order
        self.register_probe(self._python_probe)
        self.register_probe(self._toolchain_probe)
        self.register_probe(self._adb_probe)

    def register_probe(self, probe: BaseProbe) -> None:
        """Register a new diagnostic probe."""
        self._probes[probe.probe_id] = probe

    def unregister_probe(self, probe_id: str) -> None:
        """Remove a diagnostic probe."""
        self._probes.pop(probe_id, None)

    def set_probe_target_serial(self, serial: str | None) -> None:
        """Set the diagnostics probes' preferred device serial.

        This is a probe/report preference only (which device the readiness
        report highlights and verifies first). Task routing never reads it
        back: execution targets come from explicit request serials or the
        device pool. Pass None to clear the preference, e.g. after switching
        ADB server endpoints.
        """
        self.invalidate_cache()
        if hasattr(self._adb_probe, "set_target_serial"):
            self._adb_probe.set_target_serial(serial)

    async def run_probe(self, probe_id: str) -> ProbeResult | None:
        """Execute a single specific probe by ID."""
        probe = self._probes.get(probe_id)
        if not probe:
            return None
        return await probe.probe()

    async def run_device_submission_probe(self, target_serial: str | None = None) -> ProbeResult:
        """Run the bounded device gate used by task submission."""
        return await self._adb_probe.probe_submission_readiness(target_serial=target_serial)

    def invalidate_cache(self) -> None:
        """Invalidate the UI readiness snapshot after an explicit configuration change."""
        self._cache_generation += 1
        self._report_cache = None
        self._report_cache_time = 0.0
        self._report_cache_generation = -1

    def _cached_report(self, max_age_seconds: float) -> SystemReadinessReport | None:
        if self._report_cache is None:
            return None
        if self._report_cache_generation != self._cache_generation:
            return None
        if time.monotonic() - self._report_cache_time > max_age_seconds:
            return None
        return self._report_cache.model_copy(deep=True)

    async def run_all(
        self,
        categories: list[ProbeCategory] | None = None,
        *,
        force_refresh: bool = False,
    ) -> SystemReadinessReport:
        """Return a coalesced readiness snapshot.

        The dashboard polls frequently, so allowing every HTTP request to launch a
        complete toolchain and ADB scan creates a request storm. Full reports are
        cached briefly and all concurrent refreshes share one execution. The task
        submission gate remains independent and always performs its own bounded
        device check.
        """
        cacheable = categories is None
        request_started = time.monotonic()
        if cacheable and not force_refresh:
            cached = self._cached_report(self._REPORT_CACHE_TTL_SECONDS)
            if cached is not None:
                return cached

        async with self._report_lock:
            # A refresh that completed while this caller waited satisfies even a
            # forced request that began before it, coalescing concurrent clicks.
            if cacheable and self._report_cache_time >= request_started:
                cached = self._cached_report(float("inf"))
                if cached is not None:
                    return cached
            if cacheable and not force_refresh:
                cached = self._cached_report(self._REPORT_CACHE_TTL_SECONDS)
                if cached is not None:
                    return cached

            if force_refresh:
                toolchain.clear_cache()
                self._adb_probe.invalidate_enrichment_cache()

            build_generation = self._cache_generation
            report = await self._build_report(categories)
            # If a device/configuration change happened during the scan, return
            # this result only to its original caller and never publish it as the
            # shared snapshot for later requests.
            if cacheable and build_generation == self._cache_generation:
                self._report_cache = report.model_copy(deep=True)
                self._report_cache_time = time.monotonic()
                self._report_cache_generation = build_generation
            return report

    async def _build_report(
        self, categories: list[ProbeCategory] | None = None
    ) -> SystemReadinessReport:
        """Execute the underlying probes and compile an uncached report."""
        target_probes = [
            probe
            for probe in self._probes.values()
            if categories is None or probe.category in categories
        ]

        # Concurrently execute probes. A probe that raises must not take the
        # whole report down with it: it becomes a structured FAIL so the
        # remaining probes still reach the user and the verdict stays honest.
        outcomes = await asyncio.gather(
            *[
                asyncio.wait_for(probe.probe(), timeout=self.PROBE_TIMEOUT_SECONDS)
                for probe in target_probes
            ],
            return_exceptions=True,
        )
        results: list[ProbeResult] = [
            outcome
            if isinstance(outcome, ProbeResult)
            else self._crashed_probe_result(probe, outcome)
            for probe, outcome in zip(target_probes, outcomes, strict=True)
        ]

        blockers = [r for r in results if r.is_blocker]
        passed_blockers = [r for r in blockers if r.status == ProbeStatus.PASS]
        overall_ready = len(blockers) > 0 and len(blockers) == len(passed_blockers)

        # Extract active device info from ADB probe metadata if available
        active_device: DeviceInfo | None = None
        adb_result = next((r for r in results if r.id == "android_adb"), None)
        if adb_result and adb_result.metadata.get("active_device"):
            try:
                active_device = DeviceInfo(**adb_result.metadata["active_device"])
            except (TypeError, ValueError) as exc:
                # Includes pydantic ValidationError (a ValueError subclass).
                logger.warning(
                    f"Malformed active_device metadata from ADB probe; readiness"
                    f" report will omit the active device: {exc}"
                )

        return SystemReadinessReport(
            overall_ready=overall_ready,
            blocker_count=len(blockers),
            passed_blocker_count=len(passed_blockers),
            probes=results,
            active_device=active_device,
            os_type=platform.os_type.value,
            timestamp=time.time(),
        )

    @staticmethod
    def _crashed_probe_result(probe: BaseProbe, exc: object) -> ProbeResult:
        """Turn an exception escaping ``probe.probe()`` into a FAIL result.

        Cancellation and other non-``Exception`` errors are re-raised: they are
        not a diagnosis of the host, they are the event loop shutting us down.
        """
        if isinstance(exc, BaseException) and not isinstance(exc, Exception):
            raise exc
        if isinstance(exc, TimeoutError):
            logger.warning(
                f"[ReadinessEngine] Probe '{probe.probe_id}' did not finish within"
                f" {ReadinessEngine.PROBE_TIMEOUT_SECONDS:.0f}s; reporting it as FAIL."
            )
            return ProbeResult(
                id=probe.probe_id,
                category=probe.category,
                title=probe.probe_id.replace("_", " ").title(),
                status=ProbeStatus.FAIL,
                is_blocker=probe.is_blocker,
                summary="Probe timed out",
                description=(
                    f"The '{probe.probe_id}' check did not finish within"
                    f" {ReadinessEngine.PROBE_TIMEOUT_SECONDS:.0f}s. A hung ADB server is the"
                    " usual cause: restart it and run the diagnosis again."
                ),
                actions=[
                    ProbeAction(
                        action_type="command",
                        label="Restart ADB",
                        payload="adb kill-server && adb start-server",
                    ),
                ],
                metadata={
                    "exception_type": "TimeoutError",
                    "timeout_seconds": ReadinessEngine.PROBE_TIMEOUT_SECONDS,
                },
            )
        logger.warning(
            f"[ReadinessEngine] Probe '{probe.probe_id}' crashed; reporting it as FAIL: "
            f"{type(exc).__name__}: {exc}"
        )
        return ProbeResult(
            id=probe.probe_id,
            category=probe.category,
            title=probe.probe_id.replace("_", " ").title(),
            status=ProbeStatus.FAIL,
            is_blocker=probe.is_blocker,
            summary="Probe crashed",
            description=(
                f"The '{probe.probe_id}' check raised {type(exc).__name__}: {exc}. "
                "This is a diagnostics bug or a host permission problem, not a device fault."
            ),
            metadata={"exception_type": type(exc).__name__, "exception": str(exc)},
        )

    async def heal_adb_keys(self, force: bool = False) -> dict[str, Any]:
        """Auto-heal corrupted or 0-byte ADB authentication keys."""
        from bagel.diagnostics.adb_keys import heal_adb_keys

        logger.info("[ReadinessEngine] Auto-healing ADB authentication keys...")
        return await asyncio.to_thread(heal_adb_keys, None, force)


# Global singleton instance
readiness_engine = ReadinessEngine()

import { useCallback,useEffect,useState } from 'react'
import { api } from '@/lib/api'
export function useResource<T>(path:string|null, interval=0){
 const [state,setState]=useState<{path:string|null;data?:T;error?:string;loading:boolean}>({path,loading:!!path});const [version,setVersion]=useState(0)
 const refresh=useCallback(()=>setVersion(v=>v+1),[])
 useEffect(()=>{
  if(!path){setState({path,loading:false});return}
  let alive=true,busy=false;const controller=new AbortController()
  setState(previous=>({path,data:previous.path===path?previous.data:undefined,loading:true}))
  async function load(){if(busy)return;busy=true;try{const data=await api<T>(path!,{signal:controller.signal});if(alive)setState({path,data,loading:false})}catch(e){if(alive)setState(previous=>({...previous,loading:false,error:(e as Error).message}))}finally{busy=false}}
  void load();const timer=interval?setInterval(load,interval):undefined
  return()=>{alive=false;controller.abort();if(timer)clearInterval(timer)}
 },[path,interval,version])
 return {...state,data:state.path===path?state.data:undefined,error:state.path===path?state.error:undefined,refresh}
}

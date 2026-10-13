import React, {useState, useEffect, useRef} from 'react';
import {createRoot} from 'react-dom/client';
import {Theme} from '@astryxdesign/core/theme';
import {AppShell} from '@astryxdesign/core/AppShell';
import {SideNav, SideNavItem, SideNavHeading} from '@astryxdesign/core/SideNav';
import {TopNav, TopNavHeading} from '@astryxdesign/core/TopNav';
import {VStack} from '@astryxdesign/core/VStack';
import {HStack} from '@astryxdesign/core/HStack';
import {Heading} from '@astryxdesign/core/Heading';
import {Text} from '@astryxdesign/core/Text';
import {Button} from '@astryxdesign/core/Button';
import {TextInput} from '@astryxdesign/core/TextInput';
import {Selector} from '@astryxdesign/core/Selector';
import {CheckboxInput} from '@astryxdesign/core/CheckboxInput';
import {Collapsible} from '@astryxdesign/core/Collapsible';
import {Banner} from '@astryxdesign/core/Banner';
import {ProgressBar} from '@astryxdesign/core/ProgressBar';
import {popcornTheme} from './themes/popcorn.js';
import './styles.css';

const engines = {resize: 'Conventional resizing', realesrgan: 'Real-ESRGAN AI upscaling', 'rtx-vsr': 'RTX Video Super Resolution', 'dlss-sr': 'DLSS video upscaling · experimental', dlss5: 'DLSS 5 neural rendering · experimental'};
const dlssModes = {dlaa:'DLAA · keep source size',quality:'Quality · 1.5×',balanced:'Balanced · about 1.72×',performance:'Performance · 2×','ultra-performance':'Ultra Performance · 3×'};
const codecNames = {h264:'H.264',hevc:'H.265 / HEVC',av1:'AV1'};
const frameRates = ['23.976','25','29.97','30','50','59.94','60','90','119.88','120','144','165','180','240','360','480'];
const frameModes = {auto:'Auto · recommended',native:'Native · one NVIDIA pass',cascade:'Cascade · multiple NVIDIA passes'};
const motionNames = {high:'High',medium:'Balanced',low:'Fast'};
const bytes = n => n >= 1024 ** 3 ? `${(n / 1024 ** 3).toFixed(1)} GB` : `${(n / 1024 ** 2).toFixed(1)} MB`;
const navigation = [['overview','Overview'], ['library','Library'], ['processing','Processing'], ['queue','Queue'], ['settings','Settings']];
async function api(path, options = {}) {
  const response = await fetch(path, {credentials: 'same-origin', ...options, headers: {'Content-Type':'application/json', ...options.headers}});
  const data = await response.json().catch(() => ({detail:'The manager returned an unexpected response.'}));
  if (!response.ok) {
    if (response.status === 401 && path !== '/api/login') window.dispatchEvent(new Event('session-expired'));
    throw new Error(Array.isArray(data.detail) ? data.detail.map(x => x.msg).join('. ') : data.detail || 'Request failed. Try again.');
  }
  return data;
}
function Copy({children, ...props}) { return <Text as="p" color="secondary" wordBreak="break-word" {...props}>{children}</Text>; }
function PageHead({title, copy, action}) { return <div className="page-head"><VStack gap={3} className="min-w-0"><Heading level={1}>{title}</Heading><Copy>{copy}</Copy></VStack>{action}</div>; }
function Empty({title, copy, children}) { return <VStack gap={4} padding={8}><Heading level={3}>{title}</Heading><Copy>{copy}</Copy>{children}</VStack>; }
function Status({online, children, id}) { return <HStack gap={2} wrap="wrap" id={id}><span className={`status-dot ${online === true ? 'online' : online === false ? 'warning' : ''}`} aria-hidden="true"/><Text type="supporting" color="secondary">{children}</Text></HStack>; }
function Feedback({message}) { return message ? <Banner status={message.error ? 'error' : 'success'} title={message.text} collapsible={false}/> : null; }
function Login({onLogin, initialError}) {
  const [key,setKey] = useState(''), [error,setError] = useState(initialError), [busy,setBusy] = useState(false);
  async function submit(event) {
    event.preventDefault(); setBusy(true); setError('');
    try { await api('/api/login', {method:'POST', body:JSON.stringify({token:key})}); setKey(''); await onLogin(); }
    catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }
  return <div className="login-wrap"><main className="login"><VStack gap={8}>
    <Text weight="semibold">Popcorn SR</Text>
    <VStack gap={3}><Heading level={1}>Your library, improved.</Heading><Copy>Sign in to connect your library and processing devices.</Copy></VStack>
    <form onSubmit={submit}><VStack gap={5}>
      <TextInput label="Access key" type="password" value={key} onChange={value=>setKey(value)} autoComplete="current-password" isRequired description="Use the key generated during installation."/>
      {error && <Banner status="error" title={error} collapsible={false}/>}
      <Button label="Open Popcorn SR" type="submit" variant="primary" isLoading={busy} isDisabled={!key}/>
    </VStack></form>
    <Copy type="supporting">Self-hosted. Your videos stay on your devices.</Copy>
  </VStack></main></div>;
}
function Jobs({jobs, id, onAction, navigate}) {
  return <section className="panel" id={id} aria-label={id === 'jobs' ? 'Jobs' : 'Recent jobs'}>
    {!jobs.length ? <Empty title="Your first copy starts here" copy="Choose a video, try a preview, and let your worker handle the rest."><Button label="Browse library" onClick={() => navigate('library')}/></Empty> : jobs.map(job => <div className="row" key={job.id}><HStack gap={6} wrap="wrap" vAlign="start" hAlign="between">
      <VStack gap={2} className="min-w-0 flex-1 basis-60">
        <Text weight="semibold" wordBreak="break-word">{job.path.split('/').pop()}{job.recipe.preview_seconds ? ' · Preview' : ''}</Text>
        <Copy type="supporting">{engines[job.recipe.engine] || job.recipe.engine} · {codecNames[job.recipe.codec] || job.recipe.codec} / {job.recipe.engine==='dlss-sr' && job.recipe.dlss_mode?dlssModes[job.recipe.dlss_mode]:`${job.recipe.scale}×`}</Copy>
        {job.recipe.engine==='dlss-sr' && <Copy type="supporting">Preset: {job.recipe.dlss_preset && job.recipe.dlss_preset!=='default'?job.recipe.dlss_preset.toUpperCase():'Automatic'} · Motion estimation: {({high:'High',medium:'Balanced',low:'Fast'})[job.recipe.temporal_quality || 'high']}</Copy>}
        {job.recipe.frame_generation && <Copy type="supporting">DLSS frame generation: {job.recipe.frame_rate} fps · {frameModes[job.recipe.frame_generation_mode || 'auto'].split(' · ')[0]} · Motion: {motionNames[job.recipe.frame_generation_quality || 'high']}</Copy>}
        <Copy type="supporting">{job.stage}{job.status === 'running' ? ` / ${Math.floor(job.progress)}%` : ''}{job.status === 'queued' ? ' · Waiting for a compatible worker' : ''}</Copy>
        {job.error && <Banner status="error" title={job.error} collapsible={false}/>}
        {job.result && <Copy type="supporting" className="path">{job.result.path} / {bytes(job.result.bytes)}</Copy>}
        {job.status === 'running' && <ProgressBar label={`Processing ${job.path}`} value={job.progress} isLabelHidden/>}
      </VStack>
      <HStack gap={2} wrap="wrap">
        {job.status === 'completed' ? <><Button href={`/api/jobs/${job.id}/download`} label={`Download ${job.recipe.preview_seconds ? 'preview' : 'copy'}`}/>{!!job.recipe.preview_seconds && <Button variant="primary" label="Enhance full video" clickAction={() => onAction(job.id,'full')}/>}</> : ['failed','cancelled'].includes(job.status) ? <Button label="Retry" clickAction={() => onAction(job.id,'retry')}/> : <Button variant="ghost" label="Cancel" clickAction={() => onAction(job.id,'cancel')}/>}
      </HStack>
    </HStack></div>)}
  </section>;
}
function Overview({state,navigate,onAction}) {
  const online=state.workers.filter(w=>w.online && !w.revoked).length;
  return <VStack gap={10}>
    <div><PageHead title="A better home for your videos." copy="Your library stays here. The heavy lifting goes wherever you have the power."/>
    <section className="panel"><div className="welcome-grid p-6 md:p-8">
      <VStack gap={5} hAlign="start"><Heading level={2}>Give your library a clearer picture.</Heading><Copy>Make enhanced copies with a paired computer, or process everything on one device. Keep every original.</Copy><Button label="Choose a video" variant="primary" onClick={()=>navigate('library')}/></VStack>
      <VStack gap={3} aria-label="Library to processing device to finished copy">
        <VStack className="route-node" gap={1}><Text weight="semibold">Your library</Text><Copy type="supporting">NAS or this computer · Originals</Copy></VStack>
        <Copy type="supporting" justify="center">Transfer a local copy</Copy>
        <VStack className="route-node" gap={1}><Text weight="semibold">Your processing power</Text><Copy type="supporting">Paired worker or this computer · {online ? `${online} connected` : 'No worker'}</Copy></VStack>
        <Copy type="supporting" justify="center">Enhance, check, return</Copy>
        <VStack className="route-node" gap={1}><Text weight="semibold">A finished video</Text><Copy type="supporting">Saved to your output folder · New copy</Copy></VStack>
      </VStack>
    </div></section></div>
    <div className="steps">{[
      ['1. Choose your library','Browse the folder mounted during installation.','Browse library','library'],
      ['2. Connect processing','Pair a computer and choose its temporary drive.','Connect a worker','processing'],
      ['3. Preview, then enhance','Try a short clip before processing a full video.','Try a preview','library'],
    ].map(([title,copy,label,view])=><VStack key={title} gap={3} hAlign="start"><Heading level={3}>{title}</Heading><Copy>{copy}</Copy><Button label={label} variant="ghost" onClick={()=>navigate(view)}/></VStack>)}</div>
    <VStack gap={4}><HStack hAlign="between" gap={4}><Heading level={2}>Recent activity</Heading><Button label="All jobs" variant="ghost" onClick={()=>navigate('queue')}/></HStack><Jobs jobs={state.jobs.slice(0,3)} id="recent-jobs" onAction={onAction} navigate={navigate}/></VStack>
  </VStack>;
}
function Recipe({path,state,onClose,onCreated}) {
  const [desired,setDesired]=useState({worker:'',engine:'resize',scale:'2',codec:'h264',encoder:'cpu',quality:'23',dlss_mode:'performance',dlss_preset:'default',temporal_quality:'high',frame_generation:false,frame_rate:'60',frame_generation_mode:'auto',frame_generation_quality:'high',output_directory:'enhanced',denoise:false,deinterlace:false,sharpen:false,interpolate:false});
  const [error,setError]=useState(''), [busy,setBusy]=useState(false);
  const panel=useRef(null);
  useEffect(()=>{ panel.current?.scrollIntoView({block:'start',behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'}); panel.current?.querySelector('[role=combobox]')?.focus({preventScroll:true}); },[]);
  const active=state.workers.filter(w=>!w.revoked);
  const worker=active.some(w=>w.id===desired.worker)?desired.worker:'';
  const candidates=active.filter(w=>!worker || w.id===worker);
  const supported=[...new Set(candidates.flatMap(w=>w.capabilities.engines || []))];
  const engine=supported.includes(desired.engine)?desired.engine:supported[0] || 'resize';
  const capable=candidates.filter(w=>(w.capabilities.engines || []).includes(engine));
  const settings=capable.flatMap(w=>w.capabilities.dlss_sr?.settings || []);
  const modes=Object.keys(dlssModes).filter(mode=>settings.some(([m])=>m===mode));
  const advancedDLSS=engine==='dlss-sr' && modes.length>0;
  const dlssMode=modes.includes(desired.dlss_mode)?desired.dlss_mode:modes[0];
  const presets=[...new Set(settings.filter(([m])=>m===dlssMode).map(([,p])=>p))];
  const dlssPreset=presets.includes(desired.dlss_preset)?desired.dlss_preset:presets[0];
  const settingWorkers=advancedDLSS?capable.filter(w=>(w.capabilities.dlss_sr?.settings || []).some(([m,p])=>m===dlssMode && p===dlssPreset)):capable;
  const temporalQualities=[...new Set(settingWorkers.flatMap(w=>w.capabilities.dlss_sr?.temporal_qualities || []))];
  const temporalQuality=temporalQualities.includes(desired.temporal_quality)?desired.temporal_quality:temporalQualities[0];
  const matching=advancedDLSS?settingWorkers.filter(w=>(w.capabilities.dlss_sr?.temporal_qualities || []).includes(temporalQuality)):capable;
  const fgWorkers=matching.filter(w=>(w.capabilities.dlss_frame_generation?.upscalers || []).includes(engine));
  const fgSettings=fgWorkers.flatMap(w=>w.capabilities.dlss_frame_generation?.settings || []);
  const fgModes=Object.keys(frameModes).filter(mode=>fgSettings.some(([m])=>m===mode));
  const fgMode=fgModes.includes(desired.frame_generation_mode)?desired.frame_generation_mode:fgModes[0] || desired.frame_generation_mode;
  const fgQualities=['high','medium','low'].filter(q=>fgSettings.some(([m,v])=>m===fgMode && v===q));
  const fgQuality=fgQualities.includes(desired.frame_generation_quality)?desired.frame_generation_quality:fgQualities[0] || desired.frame_generation_quality;
  const generation=desired.frame_generation;
  const finalWorkers=generation?fgWorkers.filter(w=>(w.capabilities.dlss_frame_generation?.settings || []).some(([m,q])=>m===fgMode && q===fgQuality)):matching;
  const verified=[...new Set(finalWorkers.flatMap(w=>w.capabilities.encoders || []))].filter(c=>(engine==='resize' && !generation) || c.endsWith('_nvidia'));
  const codecs=[...new Set(verified.map(c=>c.split('_')[0]))];
  const codec=codecs.includes(desired.codec)?desired.codec:codecs[0] || 'h264';
  const encoders=verified.filter(c=>c.startsWith(`${codec}_`)).map(c=>c.split('_')[1]);
  const encoder=encoders.includes(desired.encoder)?desired.encoder:encoders.includes('nvidia')?'nvidia':'cpu';
  const scales=engine==='dlss5'?['1']:engine==='dlss-sr'?['1','2','3']:['1','2','3','4'];
  const scale=scales.includes(desired.scale)?desired.scale:scales[0];
  const change=(key,value)=>setDesired(current=>({...current,[key]:value,...(key==='frame_generation' && value?{interpolate:false}: {})}));
  async function submit(preview_seconds) {
    if(generation && !fgModes.length) { setError('DLSS frame generation is unavailable. Choose a compatible worker or turn off frame generation.'); return; }
    setBusy(true); setError('');
    const recipe={engine,scale:Number(scale),codec,encoder,quality:Number(desired.quality),output_directory:desired.output_directory,preview_seconds};
    if(advancedDLSS) Object.assign(recipe,{dlss_mode:dlssMode,dlss_preset:dlssPreset,temporal_quality:temporalQuality});
    if(generation) Object.assign(recipe,{frame_generation:true,frame_rate:desired.frame_rate,frame_generation_mode:fgMode,frame_generation_quality:fgQuality});
    for(const key of ['denoise','deinterlace','sharpen','interpolate']) recipe[key]=engine==='resize' && desired[key];
    if(generation) recipe.interpolate=false;
    try { await api('/api/jobs',{method:'POST',body:JSON.stringify({path,recipe,worker_id:worker || null})}); await onCreated(preview_seconds); }
    catch(e){setError(e.message);}
    finally{setBusy(false);}
  }
  return <section className="panel recipe" ref={panel} aria-label="Enhancement settings"><VStack gap={6} padding={6}>
    <HStack hAlign="between" vAlign="start" gap={4}><VStack gap={2} className="min-w-0"><Heading level={2}>Make an enhanced copy</Heading><Copy type="supporting">{path}</Copy></VStack><Button label="Close" variant="ghost" onClick={onClose}/></HStack>
    <form onSubmit={e=>{e.preventDefault();submit(5);}}><VStack gap={6}>
      <div className="form-grid">
        <Selector label="Processing device" value={worker} onChange={v=>change('worker',v)} width="100%" options={[{value:'',label:'Any compatible worker'},...active.map(w=>({value:w.id,label:w.name+(w.online?'':' (offline)')}))]} description={candidates.length?'Jobs start when a compatible device is connected.':'Connect a worker in Processing to start jobs.'}/>
        <Selector label="Enhancement" value={engine} onChange={v=>change('engine',v)} width="100%" options={(supported.length?supported:['resize']).map(e=>({value:e,label:engines[e] || e}))} description={state.engine_notes[engine]}/>
        {advancedDLSS?<Selector label="DLSS mode" value={dlssMode} onChange={v=>change('dlss_mode',v)} width="100%" options={modes.map(value=>({value,label:dlssModes[value]}))} description="Higher multipliers make a larger copy. Aspect ratio stays the same, with even dimensions for encoding."/>:<Selector label="Output size" value={scale} onChange={v=>change('scale',v)} width="100%" options={scales.map(v=>({value:v,label:({'1':'Keep source size (1×)','2':'Twice the size (2×)','3':'Three times the size (3×)','4':'Four times the size (4×)'})[v]}))} description="Aspect ratio stays the same."/>}
        <Selector label="Video format" value={codec} onChange={v=>change('codec',v)} width="100%" options={['h264','hevc','av1'].map(v=>({value:v,label:({h264:'H.264 · broad compatibility',hevc:'H.265 / HEVC · smaller files',av1:'AV1 · newer players'})[v],disabled:!codecs.includes(v)}))} description="Finished copies use a Matroska (.mkv) container."/>
      </div>
      <VStack gap={3}>
        <div className="checkbox-row"><CheckboxInput label="DLSS frame generation · experimental" value={generation} onChange={v=>change('frame_generation',v)} isDisabled={!fgModes.length && !generation}/></div>
        <Copy type="supporting">{fgModes.length?'Add NVIDIA-generated frames for smoother motion. Upscaling and frame generation can run together.':'Unavailable for this worker and enhancement. Connect a worker that passes the DLSS frame-generation check.'}</Copy>
        {generation && !fgModes.length && <Banner status="warning" title="Frame generation is unavailable" description="Your selection is kept. Choose a compatible worker or turn off frame generation to continue." collapsible={false}/>}
        {generation && <Selector label="Frame rate" value={desired.frame_rate} onChange={v=>change('frame_rate',v)} width="100%" options={frameRates.map(value=>({value,label:`${value} fps`}))} description="Choose a rate above the source. More frames take longer and can increase file size."/>}
      </VStack>
      <TextInput label="Save copies to" value={desired.output_directory} onChange={v=>change('output_directory',v)} isRequired maxLength={200} description="A folder inside your output mount. Example: enhanced/movies"/>
      {(engine!=='resize' || generation) && <Banner status="warning" title="Preview AI processing first" description="AI processing can change fine detail or appearance. Compare the preview with your original." collapsible={false}/>}
      <Collapsible trigger="More options" defaultIsOpen={false}><VStack gap={4} paddingBlockStart={4}>
        {advancedDLSS && <div className="form-grid"><Selector label="DLSS model preset" value={dlssPreset} onChange={v=>change('dlss_preset',v)} width="100%" options={presets.map(value=>({value,label:({default:'Automatic · recommended',j:'J · less ghosting, more flicker',k:'K · fine detail',l:'L · Ultra Performance default',m:'M · Performance default'})[value]}))} description="A model preference. NVIDIA may use a compatible preset instead."/><Selector label="Motion estimation" value={temporalQuality} onChange={v=>change('temporal_quality',v)} width="100%" options={['high','medium','low'].filter(v=>temporalQualities.includes(v)).map(value=>({value,label:({high:'High · most accurate',medium:'Balanced',low:'Fast · less accurate'})[value]}))} description="More accurate motion takes longer to process. Preview moving detail and scene cuts."/></div>}
        {generation && <div className="form-grid"><Selector label="Frame-generation mode" value={fgMode} onChange={v=>change('frame_generation_mode',v)} width="100%" options={(fgModes.length?fgModes:[fgMode]).map(value=>({value,label:frameModes[value]}))} isDisabled={!fgModes.length} description="Auto adds passes when needed. Native rejects rates beyond the hardware limit. Cascade uses repeated 2× passes."/><Selector label="Frame-generation motion" value={fgQuality} onChange={v=>change('frame_generation_quality',v)} width="100%" options={(fgQualities.length?fgQualities:[fgQuality]).map(value=>({value,label:motionNames[value]}))} isDisabled={!fgQualities.length} description="High takes longer. Check fast movement and scene cuts in the preview."/></div>}
        <div className="form-grid"><Selector label="Encoding hardware" value={encoder} onChange={v=>change('encoder',v)} width="100%" options={['cpu','nvidia'].map(v=>({value:v,label:v==='cpu'?'CPU':'NVIDIA GPU',disabled:!encoders.includes(v)}))} description="Only verified encoders are available."/><Selector label="Quality" value={desired.quality} onChange={v=>change('quality',v)} width="100%" options={[{value:'19',label:'High · larger file'},{value:'23',label:'Balanced'},{value:'28',label:'Compact · smaller file'}]} description="File size depends on the source and codec."/></div>
        <div className="form-grid">{[['denoise','Reduce noise'],['deinterlace','Deinterlace older video'],['sharpen','Light sharpening'],['interpolate','Smooth motion to 60 fps']].map(([key,label])=><div key={key} className="checkbox-row"><CheckboxInput label={label} value={engine==='resize' && desired[key]} onChange={v=>change(key,v)} isDisabled={engine!=='resize' || (key==='interpolate' && generation)}/></div>)}</div>
        <Copy type="supporting">Cleanup and 60 fps motion use conventional filters. Motion interpolation can be slow and changes the original cadence.</Copy>
      </VStack></Collapsible>
      {error && <Banner status="error" title={error} collapsible={false}/>}
      <Copy type="supporting">Audio, subtitles and chapters are carried into the copy. 8-bit SDR video supported in this release.</Copy>
      <HStack gap={3} wrap="wrap"><Button label="Preview 5 seconds" type="submit" variant="primary" isLoading={busy} isDisabled={!codecs.length}/><Button label="Enhance full video" onClick={()=>submit(0)} isDisabled={busy || !codecs.length || !desired.output_directory}/></HStack>
    </VStack></form>
  </VStack></section>;
}
function Library({state,navigate,onNotice,refresh}) {
  const [directory,setDirectory]=useState('.'),[offset,setOffset]=useState(0),[listing,setListing]=useState(null),[error,setError]=useState(''),[revision,setRevision]=useState(0),[selected,setSelected]=useState(null);
  useEffect(()=>{let live=true;setListing(null);setError('');api(`/api/library?directory=${encodeURIComponent(directory)}&offset=${offset}`).then(data=>{if(live)setListing(data);}).catch(e=>{if(live)setError(e.message);});return()=>{live=false;};},[directory,offset,revision]);
  function folder(path){setDirectory(path);setOffset(0);setSelected(null);}
  async function created(preview){setSelected(null);await refresh();navigate('queue');onNotice({text:preview?'Preview queued. Download it when it is ready.':'Video queued. Your original is preserved.'});}
  return <VStack gap={6}>
    <div><PageHead title="Your library" copy="Choose a video to make an enhanced copy. Originals stay untouched." action={<Button label="Refresh" onClick={()=>setRevision(v=>v+1)}/>}/>
    <section className="panel" aria-label="Library files">
      <HStack className="row" hAlign="between" gap={4} wrap="wrap"><Text type="supporting" color="secondary" className="path min-w-0">{state.storage.library}{directory==='.'?'':`/${directory}`}</Text>{directory!=='.' && <Button label="Up a folder" variant="ghost" onClick={()=>folder(directory.split('/').slice(0,-1).join('/') || '.')}/>}</HStack>
      {error?<Empty title="Library unavailable" copy={error}/>:!listing?<Empty title="Loading your library…" copy="Reading the mounted library folder."/>:!listing.items.length?<Empty title="No videos in this folder" copy="Check the library mount or open a different folder. Supported formats include MKV, MP4, MOV and WebM."/>:listing.items.map(item=><div className="row file-row" key={item.path}><Button label={item.name} variant="ghost" onClick={()=>item.directory?folder(item.path):setSelected(item.path)}><VStack gap={1} hAlign="start" className="min-w-0"><Text weight="medium" wordBreak="break-word">{item.name}</Text><Copy type="supporting">{item.directory?'Folder':bytes(item.size)}</Copy></VStack></Button>{!item.directory && <Copy type="supporting">Choose to enhance</Copy>}</div>)}
      {listing?.total>100 && <HStack className="row" gap={4} hAlign="between" wrap="wrap"><Button label="Previous" variant="ghost" isDisabled={!offset} onClick={()=>setOffset(v=>Math.max(0,v-100))}/><Copy type="supporting">{offset+1}–{Math.min(offset+100,listing.total)} of {listing.total}</Copy><Button label="Next" variant="ghost" isDisabled={offset+100>=listing.total} onClick={()=>setOffset(v=>v+100)}/></HStack>}
    </section></div>
    {selected && <Recipe key={selected} path={selected} state={state} onClose={()=>setSelected(null)} onCreated={created}/>}
  </VStack>;
}
function Processing({state,onAction,onNotice}) {
  const [pair,setPair]=useState(null), [copied,setCopied]=useState(false);
  async function connect(){try{const data=await api('/api/pair-codes',{method:'POST'});setPair(data.code);setCopied(false);}catch(e){onNotice({error:true,text:e.message});}}
  async function copy(){try{await navigator.clipboard.writeText(pair);setCopied(true);}catch{onNotice({text:'Select the pairing code and copy it manually. Automatic copying requires HTTPS or localhost.'});}}
  const workers=state.workers.filter(w=>!w.revoked);
  return <VStack gap={8}>
    <div><PageHead title="Your processing power" copy="Connect a computer on your network. It receives a copy, processes it locally, and returns the result." action={<Button label="Connect a worker" variant="primary" clickAction={connect}/>}/>
    {!workers.length?<section className="panel"><Empty title="Bring your processing power" copy="Connect your Spark, desktop or another computer. You can also run a worker beside this manager."/></section>:<div className="worker-layout">{workers.map(w=><article key={w.id} className="panel"><VStack gap={5} padding={6}>
      <HStack gap={4} hAlign="between" wrap="wrap"><Heading level={2}>{w.name}</Heading><Status online={w.online}>{w.online?'Connected':'Offline'}</Status></HStack>
      <VStack gap={1}><Copy>{w.capabilities.device}</Copy><Copy type="supporting">{w.capabilities.platform} / {w.capabilities.architecture}</Copy></VStack>
      <VStack gap={2}><Text weight="medium">Verified encoding</Text><Copy type="supporting">{(w.capabilities.encoders || []).map(c=>c.replace('_nvidia',' · NVIDIA').replace('_cpu',' · CPU').toUpperCase()).join(', ') || 'No verified encoder'}</Copy></VStack>
      <VStack gap={2}><HStack gap={4} hAlign="between" wrap="wrap"><Text weight="medium">Temporary drive</Text><Text type="supporting">{bytes(w.scratch.free_bytes || 0)} free</Text></HStack><Copy type="supporting" className="path">{w.scratch.path}</Copy></VStack>
      <VStack gap={2}><Text weight="medium">Enhancement</Text><Copy type="supporting">{(w.capabilities.engines || []).map(e=>engines[e] || e).join(', ') || 'No verified engine'}</Copy></VStack>
      {!!w.capabilities.dlss_frame_generation?.settings?.length && <VStack gap={2}><Text weight="medium">DLSS frame generation · experimental</Text><Copy type="supporting">Verified with {(w.capabilities.dlss_frame_generation.upscalers || []).map(e=>engines[e] || e).join(', ')}. Up to {w.capabilities.dlss_frame_generation.maximum_factor}× per NVIDIA pass.</Copy></VStack>}
      {!!Object.keys(w.capabilities.notes || {}).length && <Collapsible trigger="Unavailable engine details" defaultIsOpen={false}><VStack gap={3} paddingBlockStart={3}>{Object.entries(w.capabilities.notes).map(([engine,text])=><Copy key={engine} type="supporting">{engines[engine] || engine}: {text}</Copy>)}</VStack></Collapsible>}
      <Button variant="ghost" label="Disconnect worker" clickAction={()=>onAction(w.id,'revoke')}/>
    </VStack></article>)}</div>}</div>
    {pair && <section className="panel" aria-label="Pairing instructions"><VStack gap={5} padding={6}>
      <HStack gap={4} hAlign="between"><Heading level={2}>Connect your worker</Heading><Button label="Close" variant="ghost" onClick={()=>setPair(null)}/></HStack>
      <Copy>This code expires in 10 minutes and can be used once.</Copy>
      <div className="pair-code"><Text type="code" id="pair-code">{pair}</Text></div><Button label={copied?'Copied':'Copy pairing code'} clickAction={copy}/>
      <VStack gap={5}>
        <VStack gap={2}><Heading level={3}>1. On the processing computer</Heading><Copy>Install the worker using the Docker worker example. Set the manager address to <strong>{location.origin}</strong> and enter this pairing code.</Copy></VStack>
        <VStack gap={2}><Heading level={3}>2. Choose its temporary drive</Heading><Copy>Mount your Optane or another drive as the scratch folder. Mark the mounted folder with <code>init-scratch</code>. The worker will stop if that folder is unavailable.</Copy></VStack>
        <VStack gap={2}><Heading level={3}>3. Check the connection</Heading><Copy>The device appears here after its hardware tests finish. Use Ethernet for large libraries; Wi-Fi works when both devices can reach each other.</Copy></VStack>
      </VStack>
      <Button variant="ghost" label="Open installation guide" href="https://github.com/thekozugroup/Popcorn-SR/blob/main/docs/deployment.md" target="_blank" rel="noreferrer"/>
    </VStack></section>}
    <VStack gap={6} className="footnote"><VStack gap={2}><Heading level={3}>Use what your device actually supports</Heading><Copy>Encoding and AI engines appear after a real processing check. Real-ESRGAN supports Linux NVIDIA workers. RTX Video and DLSS need a separately installed, compatible processing engine.</Copy></VStack><VStack gap={2}><Heading level={3}>One device works too</Heading><Copy>Run the manager and worker together. Your library and scratch drive remain separate, even when they live on the same computer.</Copy></VStack></VStack>
  </VStack>;
}
function Settings({state,onLogout}) {
  const sections=[
    ['Library',`${state.storage.library}. Mount this folder read-only. Change the host folder in your Docker configuration.`],
    ['Finished copies',`${state.storage.output} / ${bytes(state.storage.free_bytes)} available. Choose a subfolder when creating a job. Originals are never replaced.`],
    ['Temporary storage',"Each worker owns its scratch drive. Video downloads, intermediates and uploads use that drive; small pairing credentials use its state folder. Check the host’s swap and Docker storage configuration to keep those writes off the built-in drive too."],
    ['Network','Direct Ethernet or a shared router/switch works. A plain USB-C cable does not establish a network between ordinary host ports. Wi-Fi works, with transfer speed and reliability depending on your network.'],
    ['Protected sources','This release rejects HDR and high-bit-depth input to prevent loss of color or detail. Keep your original and use a verified HDR pipeline for those files.'],
    ['Access','Keep the manager on your trusted network. Use HTTPS through a reverse proxy or VPN for remote access.'],
  ];
  return <><PageHead title="Your workspace" copy="A small manager, connected processing, and a separate home for every finished copy."/><section className="panel">{sections.map(([title,copy])=><VStack className="row" key={title} gap={3}><Heading level={2}>{title}</Heading><Copy>{copy}</Copy>{title==='Access' && <Button label="Sign out" clickAction={onLogout}/>}</VStack>)}</section></>;
}
function App() {
  const [state,setState]=useState(null),[loading,setLoading]=useState(true),[loginError,setLoginError]=useState(''),[view,setView]=useState('overview'),[notice,setNotice]=useState(null),[interrupted,setInterrupted]=useState(false),[mobileOpen,setMobileOpen]=useState(false);
  const refreshing=useRef(false), surface=useRef(null);
  const expired=()=>{setState(null);setView('overview');setNotice(null);setMobileOpen(false);};
  async function refresh(){
    if(refreshing.current)return;
    refreshing.current=true;
    try{const data=await api('/api/state');setState(data);setInterrupted(false);setLoginError('');}
    catch(e){if(state){setInterrupted(true);}else if(!e.message.includes('Sign in'))setLoginError(e.message);}
    finally{refreshing.current=false;setLoading(false);}
  }
  useEffect(()=>{refresh();window.addEventListener('session-expired',expired);return()=>window.removeEventListener('session-expired',expired);},[]);
  useEffect(()=>{if(!state)return;const poll=()=>{if(!document.hidden)refresh();};const interval=setInterval(poll,3000);document.addEventListener('visibilitychange',poll);return()=>{clearInterval(interval);document.removeEventListener('visibilitychange',poll);};},[!!state]);
  function navigate(next){setView(next);setNotice(null);setMobileOpen(false);}
  useEffect(()=>{surface.current?.focus({preventScroll:true});},[view]);
  async function onAction(id,action){
    try{await api(action==='revoke'?`/api/workers/${id}/revoke`:`/api/jobs/${id}/${action}`,{method:'POST'});await refresh();if(action==='full')setNotice({text:'Full video queued using your preview settings. Your original is preserved.'});}
    catch(e){setNotice({error:true,text:e.message});}
  }
  async function logout(){try{await api('/api/logout',{method:'POST'});expired();}catch(e){setNotice({error:true,text:e.message});}}
  if(loading)return <div className="login-wrap"><Text>Opening Popcorn SR…</Text></div>;
  if(!state)return <Login key={loginError} onLogin={refresh} initialError={loginError}/>;
  const online=state.workers.filter(w=>w.online && !w.revoked).length;
  const side=<SideNav aria-label="Main navigation" header={<SideNavHeading heading="Popcorn SR" subheading="Super Resolution"/>} footer={<VStack padding={4} gap={2}><Copy type="supporting">Version {state.version}</Copy><Button label="Sign out" variant="ghost" clickAction={logout}/></VStack>}>{navigation.map(([key,label])=><SideNavItem key={key} label={label} isSelected={view===key} onClick={()=>navigate(key)}/>)}</SideNav>;
  return <AppShell height="auto" variant="section" mobileNav={{isOpen:mobileOpen,onOpenChange:setMobileOpen}} sideNav={side} topNav={<TopNav heading={<TopNavHeading heading="Library workspace"/>} endContent={<Status id="connection" online={interrupted?false:online?true:undefined}>{interrupted?'Connection interrupted':online?`${online} worker${online===1?'':'s'} connected`:'Manager ready'}</Status>}/>}>
    <section className="workspace" ref={surface} tabIndex={-1} aria-label="Workspace"><VStack gap={6}>
      <Feedback message={notice}/>
      {interrupted && <Banner status="warning" title="Connection interrupted" description="Reconnecting automatically. Your saved jobs remain on the manager." collapsible={false}/>}
      {view==='overview' && <Overview state={state} navigate={navigate} onAction={onAction}/>}
      {view==='library' && <Library state={state} navigate={navigate} refresh={refresh} onNotice={setNotice}/>}
      {view==='processing' && <Processing state={state} onAction={onAction} onNotice={setNotice}/>}
      {view==='queue' && <><PageHead title="Your queue" copy="Follow each copy from transfer to processing to delivery." action={<Button label="Choose a video" onClick={()=>navigate('library')}/>}/>{state.jobs.some(j=>j.status==='queued') && !online && <Banner status="info" title="Jobs are waiting" description="Connect a compatible worker in Processing to continue." collapsible={false}/>}<Jobs jobs={state.jobs} id="jobs" onAction={onAction} navigate={navigate}/></>}
      {view==='settings' && <Settings state={state} onLogout={logout}/>}
    </VStack></section>
  </AppShell>;
}
createRoot(document.getElementById('root')).render(<Theme theme={popcornTheme} mode="system"><App/></Theme>);

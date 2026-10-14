import React, {useState, useEffect, useRef} from 'react';
import {createRoot} from 'react-dom/client';
import {Theme} from '@astryxdesign/core/theme';
import {VStack} from '@astryxdesign/core/VStack';
import {HStack} from '@astryxdesign/core/HStack';
import {Heading} from '@astryxdesign/core/Heading';
import {Text} from '@astryxdesign/core/Text';
import {Button} from '@astryxdesign/core/Button';
import {TextInput} from '@astryxdesign/core/TextInput';
import {NumberInput} from '@astryxdesign/core/NumberInput';
import {Selector} from '@astryxdesign/core/Selector';
import {CheckboxInput} from '@astryxdesign/core/CheckboxInput';
import {Collapsible} from '@astryxdesign/core/Collapsible';
import {Banner} from '@astryxdesign/core/Banner';
import {ProgressBar} from '@astryxdesign/core/ProgressBar';
import {Icon} from '@astryxdesign/core/Icon';
import {Badge} from '@astryxdesign/core/Badge';
import {popcornTheme} from './themes/popcorn.js';
import './styles.css';
import {passkeysSupported, usePasskey} from './passkeys.js';

const engines = {resize: 'Conventional resizing', realesrgan: 'Real-ESRGAN AI upscaling', 'rtx-vsr': 'RTX Video Super Resolution', 'dlss-sr': 'DLSS video upscaling · experimental', dlss5: 'DLSS 5 neural rendering · experimental'};
const dlssModes = {dlaa:'DLAA · keep source size',quality:'Quality · 1.5×',balanced:'Balanced · about 1.72×',performance:'Performance · 2×','ultra-performance':'Ultra Performance · 3×'};
const codecNames = {h264:'H.264',hevc:'H.265 / HEVC',av1:'AV1'};
const vsrLevels = {'1':'Level 1 · Fast','2':'Level 2 · Balanced','3':'Level 3 · High','4':'Level 4 · Ultra'};
const frameRates = ['23.976','25','29.97','30','50','59.94','60','90','119.88','120','144','165','180','240','360','480'];
const frameModes = {auto:'Auto · recommended',native:'Native · one NVIDIA pass',cascade:'Cascade · multiple NVIDIA passes'};
const motionNames = {high:'High',medium:'Balanced',low:'Fast'};
const resolutionNames = {'480':'480p','720':'720p','1080':'1080p','1440':'1440p','2160':'4K','4320':'8K',other:'Other resolutions'};
const defaultResolutionRules = {'480':'720','720':'1080','1080':'2160','1440':'2160','2160':'keep','4320':'keep',other:'keep'};
const resolution = info => info?.width && info?.height ? `${info.width} × ${info.height}` : null;
const bytes = n => n >= 1024 ** 3 ? `${(n / 1024 ** 3).toFixed(1)} GB` : `${(n / 1024 ** 2).toFixed(1)} MB`;
const workerReady = w => !w.capabilities.updates?.draining && (w.capabilities.initialization===undefined || w.capabilities.initialization==='ready');
const workerStatus = w => !w.online?'Offline':w.capabilities.updates?.draining?'Updating':w.capabilities.initialization==='checking'?'Checking support':workerReady(w)?'Connected':'Checks failed';
const updateCopy = {checking:'Checking for a release.',current:'Up to date.',waiting:'The current job finishes before updating.',installing:'Installing the update.',validating:'Checking encoding and enhancements.',updated:'Update installed.',rolled_back:'The update failed its checks. The previous version was restored.',failed:'Update check failed. Check the host update service and try again.'};
async function api(path, options = {}) {
  const response = await fetch(path, {credentials: 'same-origin', ...options, headers: {'Content-Type':'application/json', ...options.headers}});
  const data = await response.json().catch(() => ({detail:'The manager returned an unexpected response.'}));
  if (!response.ok) {
    if (response.status === 401 && !['/api/login','/api/account/password'].includes(path) && !path.startsWith('/api/auth/')) window.dispatchEvent(new Event('session-expired'));
    throw new Error(Array.isArray(data.detail) ? data.detail.map(x => x.msg).join('. ') : data.detail || 'Request failed. Try again.');
  }
  return data;
}
function Brand() {
  return <span className="brand"><svg viewBox="0 0 32 32" aria-hidden="true"><rect width="32" height="32" rx="10" fill="var(--color-text-primary)"/><circle cx="16" cy="11.7" r="4.5" fill="var(--color-background-body)"/><circle cx="11" cy="20.3" r="4.5" fill="var(--color-background-body)"/><circle cx="21" cy="20.3" r="4.5" fill="#14b8a6"/></svg><span>Popcorn <small>SR</small></span></span>;
}
function Copy({children, ...props}) { return <Text as="p" color="secondary" wordBreak="break-word" {...props}>{children}</Text>; }
function PageHead({title, copy, action}) { return <div className="page-head"><VStack gap={3} className="min-w-0"><Heading level={1}>{title}</Heading><Copy>{copy}</Copy></VStack>{action}</div>; }
function Empty({title, copy, children}) { return <VStack gap={4} padding={8}><Heading level={3}>{title}</Heading><Copy>{copy}</Copy>{children}</VStack>; }
function Status({online, children, id}) { return <HStack gap={2} wrap="wrap" vAlign="center" id={id}><span className={`status-dot ${online === true ? 'online' : online === false ? 'warning' : ''}`} aria-hidden="true"/><Text type="supporting" color="secondary">{children}</Text></HStack>; }
function Feedback({message}) { return message ? <Banner status={message.error ? 'error' : 'success'} title={message.text} collapsible={false}/> : null; }
function MediaSpec({info,format,pending=false}) {
  return <span className="media-spec"><Text type="supporting" weight="medium">{resolution(info) || 'Reading…'}{pending && resolution(info)?' · Target':''}</Text><Text type="supporting" color="secondary">{codecNames[info?.codec || format] || info?.codec || format || 'Video'}</Text></span>;
}
function InputRow({item,selected,onChoose}) {
  const row=useRef(null), [metadata,setMetadata]=useState(null), [unavailable,setUnavailable]=useState(false);
  useEffect(()=>{
    if(item.directory)return;
    let live=true, requested=false;
    const observer=new IntersectionObserver(entries=>{
      if(!requested && entries.some(entry=>entry.isIntersecting)) {
        requested=true;observer.disconnect();
        api(`/api/library/metadata?path=${encodeURIComponent(item.path)}`).then(info=>{if(live)setMetadata(info);}).catch(()=>{if(live)setUnavailable(true);});
      }
    },{root:row.current.closest('.pane-content')});
    observer.observe(row.current);
    return()=>{live=false;observer.disconnect();};
  },[item.path,item.modified_ns,item.directory]);
  return <div ref={row} className={`row file-row ${selected?'selected-file':''}`}>
    <Button label={item.name} variant="ghost" className="input-choice" width="100%" aria-pressed={item.directory?undefined:selected} onClick={onChoose}><span className="file-content">
      {!item.directory && <span className="file-selection" aria-hidden="true">{selected && <Icon icon="check" size="sm"/>}</span>}
      <Text weight="medium" className="path file-name">{item.name}</Text>
      {item.directory?<Icon icon="chevronRight" color="secondary"/>:unavailable?<span className="media-spec"><Text type="supporting" color="secondary">Details unavailable</Text></span>:<MediaSpec info={metadata} format={item.name.split('.').pop().toUpperCase()}/>}
    </span></Button>
  </div>;
}
function PasswordForm({account,onSaved}) {
  const [username,setUsername]=useState(account.username || 'admin'), [password,setPassword]=useState(''), [confirmation,setConfirmation]=useState(''), [current,setCurrent]=useState(''), [busy,setBusy]=useState(false), [error,setError]=useState('');
  async function submit(event){event.preventDefault();setError('');if(password!==confirmation){setError('The passwords do not match. Enter them again.');return;}setBusy(true);try{await api('/api/account/password',{method:'POST',body:JSON.stringify({username,password,current_password:current})});setPassword('');setConfirmation('');setCurrent('');await onSaved();}catch(e){setError(e.message);}finally{setBusy(false);}}
  return <form onSubmit={submit}><VStack gap={5}>
    <TextInput label="Username" value={username} onChange={setUsername} autoComplete="username" isRequired/>
    {!account.must_change_password && <TextInput label="Current password" type="password" value={current} onChange={setCurrent} autoComplete="current-password" isRequired/>}
    <TextInput label="New password" type="password" value={password} onChange={setPassword} autoComplete="new-password" isRequired description="At least 6 characters."/>
    <TextInput label="Confirm password" type="password" value={confirmation} onChange={setConfirmation} autoComplete="new-password" isRequired/>
    {error && <Banner status="error" title={error} collapsible={false}/>}
    <Button label="Save password" variant="primary" type="submit" isLoading={busy} isDisabled={!username || password.length<6 || !confirmation || (!account.must_change_password && !current)}/>
  </VStack></form>;
}
function Login({account,onLogin,initialError}) {
  const [username,setUsername]=useState(account?.default_login?'admin':''), [password,setPassword]=useState(''), [error,setError]=useState(initialError), [busy,setBusy]=useState(false);
  const changing=account?.authenticated && account.must_change_password, offering=account?.authenticated && account.offer_passkey && !changing;
  const canPasskey=account?.passkey_available && passkeysSupported();
  async function submit(event){event.preventDefault();setBusy(true);setError('');try{await api('/api/login',{method:'POST',body:JSON.stringify({username,password})});setPassword('');await onLogin();}catch(e){setError(e.message);}finally{setBusy(false);}}
  async function passkey(register){setBusy(true);setError('');try{await usePasskey(api,register);await onLogin();}catch(e){setError(e.message);}finally{setBusy(false);}}
  async function skip(){setBusy(true);setError('');try{await api('/api/auth/passkeys/skip',{method:'POST'});await onLogin();}catch(e){setError(e.message);}finally{setBusy(false);}}
  return <div className="login-wrap"><main className="login"><VStack gap={8}>
    <Brand/>
    <VStack gap={3}><Heading level={1}>{changing?'Make it yours':offering?'Add a passkey':'Welcome to Popcorn SR'}</Heading><Copy>{changing?'Change the initial password to open your workspace.':offering?'Next time, sign in with your fingerprint, face or device PIN.':'Sign in to your workspace.'}</Copy></VStack>
    {changing?<PasswordForm account={account} onSaved={onLogin}/>:offering?<VStack gap={5}>
      {canPasskey?<Button label="Create a passkey" variant="primary" isLoading={busy} onClick={()=>passkey(true)}/>:<Copy>{account.passkey_url?<><a href={account.passkey_url}>Open the secure address</a> and sign in to create a passkey.</>:'Passkeys need a secure address. Set an HTTPS address for this installation, then add one in Devices & storage.'}</Copy>}
      {error && <Banner status="error" title={error} collapsible={false}/>}
      <Button label="Not now" variant="ghost" isDisabled={busy} onClick={skip}/>
    </VStack>:<form onSubmit={submit}><VStack gap={5}>
      <TextInput label="Username" value={username} onChange={setUsername} autoComplete="username" isRequired/>
      <TextInput label="Password" type="password" value={password} onChange={setPassword} autoComplete="current-password" isRequired/>
      {account?.default_login && <Copy type="supporting">First sign-in: admin / admin. You’ll choose a new password next.</Copy>}
      {error && <Banner status="error" title={error} collapsible={false}/>}
      <Button label="Sign in" type="submit" variant="primary" isLoading={busy} isDisabled={!username || !password}/>
      {canPasskey && account.has_passkeys && <Button label="Sign in with a passkey" variant="ghost" isDisabled={busy} onClick={()=>passkey(false)}/>}
    </VStack></form>}
    <Copy type="supporting">Your videos stay on your devices.</Copy>
  </VStack></main></div>;
}
function Jobs({jobs,onAction,onCompare}) {
  return <div id="jobs" className="pane-content" aria-label="Output jobs">
    {!jobs.length ? <Empty title="Your processed videos" copy="Select an input and add it to the queue. Finished copies appear here."/> : jobs.map(job => <article className="row job-row" key={job.id} data-job-id={job.id} aria-label={job.path.split('/').pop()}>
      <div className="media-heading"><VStack gap={1} className="min-w-0"><Text weight="medium" className="path">{job.path.split('/').pop()}</Text><Text type="supporting" color="secondary" className="job-status">{({completed:'Ready',failed:'Failed',cancelled:'Cancelled',queued:'Queued',running:`Processing · ${Math.floor(job.progress)}%`})[job.status] || job.status}{job.recipe.preview_seconds?' · Preview':''}</Text></VStack>{(job.result || job.planned_output) && <MediaSpec info={job.result || job.planned_output} format={job.recipe.codec} pending={!job.result}/>}</div>
      {['queued','running'].includes(job.status) && <Copy type="supporting">{job.status==='queued'?'Waiting for a compatible device':job.stage}</Copy>}
      {job.status==='running' && <ProgressBar label={`Processing ${job.path}`} value={job.progress} isLabelHidden/>}
      {job.error && <Banner status="error" title={job.error} collapsible={false}/>}
      <HStack gap={2} wrap="wrap">
        {job.status==='completed'?<><Button href={`/api/jobs/${job.id}/download`} label={`Download ${job.recipe.preview_seconds?'preview':'copy'}`}/>{!!job.recipe.preview_seconds && <>{!job.recipe.hdr && <Button label="Compare frame" onClick={()=>onCompare(job)}/>} {job.recipe.preview_frame_time==null && <Button label="Enhance full video" clickAction={()=>onAction(job.id,'full')}/>}</>}</>:['failed','cancelled'].includes(job.status)?<Button label="Retry" clickAction={()=>onAction(job.id,'retry')}/>:<Button variant="ghost" label="Cancel" clickAction={()=>onAction(job.id,'cancel')}/>}
        <Collapsible trigger={<Text type="supporting">Details</Text>} defaultIsOpen={false}><VStack gap={2} paddingBlockStart={2}>
          <Copy type="supporting">{engines[job.recipe.engine] || job.recipe.engine} · {codecNames[job.recipe.codec] || job.recipe.codec} / {job.recipe.output_width?`${job.recipe.output_width} × ${job.recipe.output_height} px`:job.recipe.engine==='dlss-sr' && job.recipe.dlss_mode?dlssModes[job.recipe.dlss_mode]:`${job.recipe.scale}×`}</Copy>
          {job.recipe.engine==='rtx-vsr' && <Copy type="supporting">VSR quality: {job.recipe.vsr_quality?vsrLevels[job.recipe.vsr_quality]:'Worker default'}{job.recipe.vsr_strength!=null?` · Strength: ${Math.round(job.recipe.vsr_strength*100)}%`:''}</Copy>}
          {job.recipe.engine==='dlss-sr' && <Copy type="supporting">Preset: {job.recipe.dlss_preset && job.recipe.dlss_preset!=='default'?job.recipe.dlss_preset.toUpperCase():'Automatic'} · Motion estimation: {motionNames[job.recipe.temporal_quality || 'high']}</Copy>}
          {job.recipe.frame_generation && <Copy type="supporting">DLSS frame generation: {job.recipe.frame_rate} fps · {frameModes[job.recipe.frame_generation_mode || 'auto'].split(' · ')[0]} · Motion: {motionNames[job.recipe.frame_generation_quality || 'high']}</Copy>}
          {job.recipe.hdr && <Copy type="supporting">RTX Video HDR · 10-bit · Peak brightness: {job.recipe.hdr_luminance || 650} nits</Copy>}
          {job.source && <Copy type="supporting">Original: {resolution(job.source)}{job.result?` · Output: ${resolution(job.result)}`:''}</Copy>}
          {job.result && <Copy type="supporting" className="path">{job.result.path}</Copy>}
        </VStack></Collapsible>
      </HStack>
    </article>)}
  </div>;
}
function Recipe({paths,state,onCreated,compareJob}) {
  const [chosen,setChosen]=useState(null), [frameTime,setFrameTime]=useState(0), [info,setInfo]=useState(null), [frameError,setFrameError]=useState(''), [review,setReview]=useState(null), [loaded,setLoaded]=useState({});
  const path=paths.includes(chosen)?chosen:paths[0] || null;
  const panel=useRef(null);
  const [expanded,setExpanded]=useState(false);
  useEffect(()=>{const changed=()=>setExpanded(document.fullscreenElement===panel.current);document.addEventListener('fullscreenchange',changed);return()=>document.removeEventListener('fullscreenchange',changed);},[]);
  async function expand(){try{if(document.fullscreenElement===panel.current)await document.exitFullscreen();else await panel.current.requestFullscreen();}catch{setFrameError('Expanded view is unavailable in this browser. Use browser zoom for a larger comparison.');}}
  useEffect(()=>{let live=true;setInfo(null);setFrameError('');setLoaded({});
    if(path) api(`/api/library/info?path=${encodeURIComponent(path)}`).then(v=>{if(live)setInfo(v);}).catch(e=>{if(live)setFrameError(e.message);});
    return()=>{live=false;};
  },[path]);
  useEffect(()=>{if(compareJob?.path===path && review?.id===compareJob.id)return;setFrameTime(0);setReview(null);},[path]);
  const [desired,setDesired]=useState({worker:'',engine:'auto',scale:'2',size_mode:'scale',resolution_rules:defaultResolutionRules,output_width:1920,output_height:1080,vsr_quality:'default',vsr_strength:null,codec:'h264',encoder:'auto',quality:'23',dlss_mode:'performance',dlss_preset:'default',temporal_quality:'high',frame_generation:false,frame_rate:'60',frame_generation_mode:'auto',frame_generation_quality:'high',hdr:false,hdr_contrast:100,hdr_saturation:100,hdr_middle_gray:50,hdr_luminance:650,hdr_debanding:true,output_directory:'enhanced',denoise:false,deinterlace:false,sharpen:false,interpolate:false});
  const [error,setError]=useState(''), [busy,setBusy]=useState(false);
  useEffect(()=>{
    if(!compareJob)return;
    const r=compareJob.recipe;
    const restored={...desired,...r,resolution_rules:r.resolution_rules || defaultResolutionRules,worker:compareJob.target || '',scale:String(r.scale),quality:String(r.quality),vsr_quality:r.vsr_quality?String(r.vsr_quality):'default',vsr_strength:r.vsr_strength==null?null:r.vsr_strength*100,size_mode:r.resolution_rules?'rules':r.output_width?'custom':'scale',dlss_mode:r.dlss_mode || 'performance'};
    delete restored.preview_seconds;delete restored.preview_frame_time;
    delete restored.target_resolution;
    setDesired(restored);setChosen(compareJob.path);setFrameTime(r.preview_frame_time || 0);
    setReview({id:compareJob.id,path:compareJob.path,time:r.preview_frame_time || 0,selection:JSON.stringify(restored)});
    panel.current?.scrollIntoView({block:'start',behavior:'auto'});
  },[compareJob]);

  const active=state.workers.filter(w=>!w.revoked);
  const worker=active.some(w=>w.id===desired.worker)?desired.worker:'';
  const selected=active.filter(w=>!worker || w.id===worker);
  const candidates=selected.filter(workerReady);
  const checking=selected.some(w=>w.capabilities.initialization==='checking');
  const failed=selected.some(w=>w.capabilities.initialization==='failed');
  const supported=[...new Set(candidates.flatMap(w=>w.capabilities.engines || []))];
  const engine=desired.engine==='auto'?['dlss-sr','rtx-vsr','realesrgan','resize'].find(e=>supported.includes(e)) || 'resize':desired.engine;
  const engineUnavailable=desired.engine!=='auto' && !supported.includes(desired.engine);
  const rulesEnabled=desired.size_mode==='rules';
  const capable=candidates.filter(w=>(w.capabilities.engines || []).includes(engine) && (!rulesEnabled || (w.capabilities.resolution_rules && (engine!=='dlss-sr' || w.capabilities.dlss_sr?.resolution_targets) && (engine!=='rtx-vsr' || w.capabilities.rtx_vsr?.custom_size))));
  const settings=capable.flatMap(w=>w.capabilities.dlss_sr?.settings || []);
  const modes=Object.keys(dlssModes).filter(mode=>settings.some(([m])=>m===mode));
  const advancedDLSS=engine==='dlss-sr' && modes.length>0;
  const dlssMode=modes.includes(desired.dlss_mode)?desired.dlss_mode:modes[0];
  const presets=[...new Set(settings.filter(([m])=>m===dlssMode).map(([,p])=>p))];
  const dlssPreset=presets.includes(desired.dlss_preset)?desired.dlss_preset:presets[0];
  const settingWorkers=advancedDLSS?capable.filter(w=>(w.capabilities.dlss_sr?.settings || []).some(([m,p])=>m===dlssMode && p===dlssPreset)):capable;
  const temporalQualities=[...new Set(settingWorkers.flatMap(w=>w.capabilities.dlss_sr?.temporal_qualities || []))];
  const temporalQuality=temporalQualities.includes(desired.temporal_quality)?desired.temporal_quality:temporalQualities[0];
  const vsr=engine==='rtx-vsr';
  const vsrRequested=vsr || desired.engine==='rtx-vsr';
  const vsrQualities=[...new Set(capable.flatMap(w=>w.capabilities.rtx_vsr?.qualities || []))].map(String);
  const customSize=vsrRequested && desired.size_mode==='custom';
  const vsrControls=vsrRequested && (desired.vsr_quality!=='default' || desired.vsr_strength!==null || customSize);
  const vsrWorkers=capable.filter(w=>!vsrControls || ((desired.vsr_quality==='default' || w.capabilities.rtx_vsr?.qualities?.includes(Number(desired.vsr_quality))) && (desired.vsr_strength===null || w.capabilities.rtx_vsr?.strength) && (!customSize || w.capabilities.rtx_vsr?.custom_size)));
  const vsrUnavailable=vsrRequested && (!vsr || !vsrWorkers.length);
  const sizeInvalid=customSize && ![desired.output_width,desired.output_height].every(v=>Number.isInteger(v) && v>=64 && v<=7680 && v%8===0);
  const matching=advancedDLSS?settingWorkers.filter(w=>(w.capabilities.dlss_sr?.temporal_qualities || []).includes(temporalQuality)):vsrRequested?vsrUnavailable?[]:vsrWorkers:capable;
  const fgWorkers=matching.filter(w=>(!vsr || w.capabilities.rtx_vsr?.lossless) && (w.capabilities.dlss_frame_generation?.upscalers || []).includes(engine));
  const fgSettings=fgWorkers.flatMap(w=>w.capabilities.dlss_frame_generation?.settings || []);
  const fgModes=Object.keys(frameModes).filter(mode=>fgSettings.some(([m])=>m===mode));
  const fgMode=fgModes.includes(desired.frame_generation_mode)?desired.frame_generation_mode:fgModes[0] || desired.frame_generation_mode;
  const fgQualities=['high','medium','low'].filter(q=>fgSettings.some(([m,v])=>m===fgMode && v===q));
  const fgQuality=fgQualities.includes(desired.frame_generation_quality)?desired.frame_generation_quality:fgQualities[0] || desired.frame_generation_quality;
  const generation=desired.frame_generation;
  const frameWorkers=generation?fgWorkers.filter(w=>(w.capabilities.dlss_frame_generation?.settings || []).some(([m,q])=>m===fgMode && q===fgQuality)):matching;
  const hdrWorkers=frameWorkers.filter(w=>(!vsr || w.capabilities.rtx_vsr?.lossless) && (w.capabilities.rtx_hdr?.pipelines || []).some(([e,g])=>e===engine && g===generation));
  const hdr=desired.hdr;
  const finalWorkers=hdr?hdrWorkers:frameWorkers;
  const verified=[...new Set(finalWorkers.flatMap(w=>(w.capabilities.encoders || []).filter(c=>(!vsrControls || w.capabilities.rtx_vsr?.codecs?.includes(c.split('_')[0])) && (!hdr || (w.capabilities.rtx_hdr?.pipelines || []).some(([e,g,codec])=>e===engine && g===generation && c===`${codec}_nvidia`)))))].filter(c=>(engine==='resize' && !generation && !hdr) || c.endsWith('_nvidia'));
  const codecs=[...new Set(verified.map(c=>c.split('_')[0]))];
  const codec=codecs.includes(desired.codec)?desired.codec:codecs[0] || 'h264';
  const encoders=verified.filter(c=>c.startsWith(`${codec}_`)).map(c=>c.split('_')[1]);
  const encoder=encoders.includes(desired.encoder)?desired.encoder:encoders.includes('nvidia')?'nvidia':'cpu';
  const scales=engine==='dlss5'?['1']:engine==='dlss-sr'?['1','2','3']:['1','2','3','4'];
  const scale=scales.includes(desired.scale)?desired.scale:scales[0];
  const change=(key,value)=>setDesired(current=>({...current,[key]:value,...(key==='frame_generation' && value?{interpolate:false}: {})}));
  const effectiveRecipe={engine,scale:Number(scale),codec,encoder,quality:Number(desired.quality),output_directory:desired.output_directory};
  if(rulesEnabled) effectiveRecipe.resolution_rules=desired.resolution_rules;
  if(advancedDLSS) Object.assign(effectiveRecipe,{dlss_mode:dlssMode,dlss_preset:dlssPreset,temporal_quality:temporalQuality});
  if(vsr && desired.vsr_quality!=='default') effectiveRecipe.vsr_quality=Number(desired.vsr_quality);
  if(vsr && desired.vsr_strength!==null) effectiveRecipe.vsr_strength=desired.vsr_strength/100;
  if(customSize) Object.assign(effectiveRecipe,{output_width:desired.output_width,output_height:desired.output_height});
  if(generation) Object.assign(effectiveRecipe,{frame_generation:true,frame_rate:desired.frame_rate,frame_generation_mode:fgMode,frame_generation_quality:fgQuality});
  if(hdr) Object.assign(effectiveRecipe,{hdr:true,...Object.fromEntries(['hdr_contrast','hdr_saturation','hdr_middle_gray','hdr_luminance','hdr_debanding'].map(key=>[key,desired[key]]))});
  for(const key of ['denoise','deinterlace','sharpen','interpolate']) effectiveRecipe[key]=engine==='resize' && desired[key];
  if(generation) effectiveRecipe.interpolate=false;
  async function submit(preview_seconds, frame=false, reviewed=false) {
    if(reviewed && (!comparisonReady || loaded.Original!==originalURL || loaded.Enhanced!==enhancedURL))return;
    if(!path || busy || engineUnavailable || !codecs.length || !desired.output_directory.trim()) return;
    if(vsrUnavailable || sizeInvalid) { setError('Choose verified RTX Video settings and dimensions that are multiples of 8.'); return; }
    if(generation && !fgModes.length) { setError('DLSS frame generation is unavailable. Choose a compatible worker or turn off frame generation.'); return; }
    if(hdr && !hdrWorkers.length) { setError('RTX Video HDR is unavailable. Choose a compatible worker or turn off HDR.'); return; }
    setBusy(true); setError('');
    const recipe={...effectiveRecipe,preview_seconds};
    if(frame) recipe.preview_frame_time=frameTime;
    try {
      if(preview_seconds) {
        const job=await api('/api/jobs',{method:'POST',body:JSON.stringify({path,recipe,worker_id:worker || null})});
        if(frame)setReview({id:job.id,path,time:frameTime,selection:JSON.stringify(desired)});
        await onCreated(preview_seconds,false);
      } else {
        let completed=0;
        for(const input of paths) {
          if(reviewed && input===review.path) await api(`/api/jobs/${review.id}/full`,{method:'POST'});
          else await api('/api/jobs',{method:'POST',body:JSON.stringify({path:input,recipe,worker_id:worker || null})});
          completed++;
          await onCreated(0,completed===paths.length,input);
        }
      }
    }
    catch(e){setError(e.message);}
    finally{setBusy(false);}
  }
  const reviewedJob=review && state.jobs.find(j=>j.id===review.id);
  const effectiveMatch=!reviewedJob || (reviewedJob.target===(worker || null) && Object.entries(effectiveRecipe).every(([key,value])=>rulesEnabled && ['scale','dlss_mode'].includes(key) || JSON.stringify(reviewedJob.recipe[key])===JSON.stringify(value)));
  const currentReview=review && review.path===path && review.time===frameTime && review.selection===JSON.stringify(desired) && effectiveMatch;
  const comparisonReady=currentReview && reviewedJob?.status==='completed';
  const originalURL=path && info && Number.isFinite(frameTime) && frameTime>=0 && frameTime<info.duration?comparisonReady?`/api/jobs/${review.id}/frame?side=original`:`/api/library/frame?path=${encodeURIComponent(path)}&seconds=${frameTime}`:null;
  const enhancedURL=comparisonReady?`/api/jobs/${review.id}/frame?side=enhanced`:null;
  const canPreview=!!path && !busy && !!codecs.length && !engineUnavailable && !vsrUnavailable && !sizeInvalid && (!generation || !!fgModes.length) && (!hdr || !!hdrWorkers.length) && !!desired.output_directory.trim();
  return <>
    {path && <section className="panel frame-preview" aria-label="Frame comparison" ref={panel}><VStack gap={5} padding={6}>
      <HStack hAlign="between" gap={3} wrap="wrap"><div><Heading level={2}>Compare a frame</Heading><Copy>Preview one moment before running the full video.</Copy></div>{document.fullscreenEnabled && <Button label={expanded?'Exit expanded preview':'Expand preview'} variant="ghost" onClick={expand}/>}</HStack>
      <div className="frame-controls">
        {paths.length>1 && <Selector label="Preview video" value={path} onChange={setChosen} width="100%" options={paths.map(value=>({value,label:value.split('/').pop()}))}/>}
        <NumberInput label="Frame at" value={frameTime} onChange={v=>{setFrameTime(v);setLoaded({});setFrameError('');}} min={0} max={info?Math.max(0,info.duration-.05):undefined} step={1} units={info?'seconds':undefined} isWheelEnabled={false} width="100%" isDisabled={!info}/>
        <Button label="Preview frame" onClick={()=>submit(5,true)} isLoading={busy} isDisabled={!canPreview || !info || !Number.isFinite(frameTime) || frameTime<0 || frameTime>=info.duration || hdr}/>
      </div>
      <div className="frame-pair">
        {[['Original',originalURL,info],['Enhanced',enhancedURL,reviewedJob?.result]].map(([label,url,dimensions])=><figure key={label}>
          <figcaption><Text weight="medium">{label}</Text>{url && dimensions && <Text type="supporting" color="secondary">{dimensions.width} × {dimensions.height}</Text>}</figcaption>
          <div className="frame-image">{url?<img key={url} src={url} alt={`${label} frame from ${path.split('/').pop()} at ${frameTime} seconds`} onLoad={()=>setLoaded(v=>({...v,[label]:url}))} onError={()=>{setLoaded(v=>({...v,[label]:null}));setFrameError('Frame unavailable. Choose another time or create a new preview.');}}/>:<Copy type="supporting">{label==='Original'?'Choose a time in this video.':reviewedJob && currentReview && !['failed','cancelled'].includes(reviewedJob.status)?'Processing your preview…':'Your processed frame appears here.'}</Copy>}</div>
        </figure>)}
      </div>
      {frameError && <Banner status="error" title={frameError} collapsible={false}/>}
      {currentReview && reviewedJob?.error && <Banner status="error" title={reviewedJob.error} collapsible={false}/>}
      {currentReview && reviewedJob && ['queued','running'].includes(reviewedJob.status) && <Copy role="status">{reviewedJob.stage}{reviewedJob.status==='running'?` · ${Math.floor(reviewedJob.progress)}%`:''}</Copy>}
      {review && !currentReview && <Copy role="status">The frame or settings changed. Preview again to compare this selection.</Copy>}
      {hdr && <Copy>Review HDR in a video preview on an HDR display. Still comparison supports SDR.</Copy>}
      <div className="recipe-actions"><Copy type="supporting">{paths.length>1?`${paths.length} videos selected. This frame previews ${path.split('/').pop()}.`:'Preview uses a short video sample. Your original stays untouched.'}</Copy><Button label={paths.length>1?'Run full batch':'Run full video'} variant="primary" onClick={()=>submit(0,false,true)} isLoading={busy} isDisabled={!canPreview || !comparisonReady || loaded.Original!==originalURL || loaded.Enhanced!==enhancedURL}/></div>
    </VStack></section>}
    <section className="recipe" aria-label="Upscaling settings"><VStack gap={5}>
    <Heading level={2}>Upscaling settings</Heading>
    <form onSubmit={e=>{e.preventDefault();submit(0);}}><VStack gap={6}>
      <div className="settings-grid">
        <Selector label="Enhancement" value={engine} onChange={v=>change('engine',v)} width="100%" options={[...new Set([...supported,engine])].map(e=>({value:e,label:engines[e] || e,disabled:!supported.includes(e)}))}/>
        {rulesEnabled?<VStack gap={1} className="rule-summary"><Text weight="medium">Output size</Text><Copy>By input resolution</Copy><Copy type="supporting">Set each target below.</Copy></VStack>:advancedDLSS?<Selector label="DLSS mode" value={dlssMode} onChange={v=>change('dlss_mode',v)} width="100%" options={modes.map(value=>({value,label:dlssModes[value]}))}/>:<Selector label="Output size" value={customSize?'custom':scale} onChange={v=>v==='custom'?change('size_mode','custom'):setDesired(current=>({...current,size_mode:'scale',scale:v}))} width="100%" options={[...scales.map(v=>({value:v,label:({'1':'Keep source size (1×)','2':'Twice the size (2×)','3':'Three times the size (3×)','4':'Four times the size (4×)'})[v]})),...(vsr && capable.some(w=>w.capabilities.rtx_vsr?.custom_size) || customSize?[{value:'custom',label:'Custom dimensions'}]:[])]}/>}
        <Selector label="Video format" value={codec} onChange={v=>change('codec',v)} width="100%" options={['h264','hevc','av1'].map(v=>({value:v,label:({h264:'H.264 · broad compatibility',hevc:'H.265 / HEVC · smaller files',av1:'AV1 · newer players'})[v],disabled:!codecs.includes(v)}))}/>
      </div>
      <Collapsible trigger="Resolution rules" defaultIsOpen={false}><VStack gap={4} paddingBlockStart={4}>
        <div className="checkbox-row"><CheckboxInput label="Set output by input resolution" value={rulesEnabled} onChange={value=>change('size_mode',value?'rules':'scale')} isDisabled={engine==='dlss5'}/></div>
        <Copy type="supporting">Each video uses its matching rule. Cropped and portrait videos keep their shape. Unmatched resolutions keep their original size.</Copy>
        {rulesEnabled && <><div className="resolution-rules">{Object.entries(resolutionNames).filter(([key])=>key!=='other').map(([key,label])=><div className="resolution-rule" key={key}><Text weight="medium">{label} input</Text><Icon icon="chevronRight" color="secondary"/><Selector label={`${label} output`} isLabelHidden value={desired.resolution_rules[key]} onChange={value=>setDesired(current=>({...current,resolution_rules:{...current.resolution_rules,[key]:value}}))} width="100%" options={[{value:'keep',label:'Keep resolution'},...Object.entries(resolutionNames).filter(([value])=>value!=='other' && Number(value)>Number(key)).map(([value,label])=>({value,label}))]}/></div>)}</div>{engine==='dlss-sr' && <Copy type="supporting">DLSS uses a verified mode, then fits the enhanced picture to your target. Targets above 3× need another enhancement.</Copy>}</>}
      </VStack></Collapsible>
      {vsrRequested && <VStack gap={3}><Selector label="VSR quality" value={desired.vsr_quality} onChange={v=>change('vsr_quality',v)} width="100%" options={[{value:'default',label:'Worker default'},...Object.entries(vsrLevels).filter(([value])=>vsrQualities.includes(value) || value===desired.vsr_quality).map(([value,label])=>({value,label,disabled:!vsrQualities.includes(value)}))]} description="Higher levels favor detail and take longer. This controls enhancement; export quality controls file size."/>{customSize && <div className="form-grid">{[['output_width','Output width'],['output_height','Output height']].map(([key,label])=><NumberInput key={key} label={label} value={desired[key]} onChange={v=>change(key,v)} min={64} max={7680} step={8} units="px" isIntegerOnly isWheelEnabled={false} width="100%" description="64–7680 pixels, in multiples of 8."/>)}</div>}{sizeInvalid && <Banner status="warning" title="Check the output dimensions" description="Enter both dimensions as multiples of 8, from 64 to 7680 pixels." collapsible={false}/>}{vsrUnavailable && <Banner status="warning" title="RTX Video settings are unavailable" description="Your choices are kept. Choose a compatible worker or change the enhancement settings." collapsible={false}/>}</VStack>}
      <Collapsible trigger="More options" defaultIsOpen={false}><VStack gap={4} paddingBlockStart={4}>
        <Selector label="Processing device" value={worker} onChange={v=>change('worker',v)} width="100%" options={[{value:'',label:'Any compatible worker'},...active.map(w=>({value:w.id,label:w.name+(workerStatus(w)==='Connected'?'':` (${workerStatus(w).toLowerCase()})`)}))]} description={candidates.length?'Jobs start when a compatible device is connected.':checking?'Support checks are running. Options become available when they finish.':failed?'Support checks failed. Open Devices & storage for the reason.':'Connect a device in Devices & storage to start jobs.'}/>
      <VStack gap={3}>
        <div className="checkbox-row"><CheckboxInput label="DLSS frame generation · experimental" value={generation} onChange={v=>change('frame_generation',v)} isDisabled={!fgModes.length && !generation}/></div>
        <Copy type="supporting">{fgModes.length?'Add NVIDIA-generated frames for smoother motion. Upscaling and frame generation can run together.':'Unavailable for this worker and enhancement. Connect a worker that passes the DLSS frame-generation check.'}</Copy>
        {generation && !fgModes.length && <Banner status="warning" title="Frame generation is unavailable" description="Your selection is kept. Choose a compatible worker or turn off frame generation to continue." collapsible={false}/>}
        {generation && <Selector label="Frame rate" value={desired.frame_rate} onChange={v=>change('frame_rate',v)} width="100%" options={frameRates.map(value=>({value,label:`${value} fps`}))} description="Choose a rate above the source. More frames take longer and can increase file size."/>}
      </VStack>
      <VStack gap={3}>
        <div className="checkbox-row"><CheckboxInput label="RTX Video HDR · experimental" value={hdr} onChange={v=>change('hdr',v)} isDisabled={!hdrWorkers.length && !hdr}/></div>
        <Copy type="supporting">{hdrWorkers.length?'Convert SDR video to HDR with NVIDIA. Saves a 10-bit H.265 or AV1 copy. Compare it on an HDR display.':'Unavailable for this worker and enhancement. Connect a worker that passes the HDR conversion and export checks.'}</Copy>
        {hdr && !hdrWorkers.length && <Banner status="warning" title="HDR is unavailable" description="Your selection is kept. Choose a compatible worker or turn off HDR to continue." collapsible={false}/>}
      </VStack>
      <TextInput label="Save copies to" value={desired.output_directory} onChange={v=>change('output_directory',v)} isRequired maxLength={200} description="Inside your output folder. Example: enhanced/movies"/>

        {vsr && (capable.some(w=>w.capabilities.rtx_vsr?.strength) || desired.vsr_strength!==null) && <NumberInput label="VSR strength" value={desired.vsr_strength===null?100:desired.vsr_strength} onChange={v=>change('vsr_strength',v)} min={0} max={100} step={1} units="%" isIntegerOnly isWheelEnabled={false} width="100%" description="Lower reduces enhancement. Default: 100%. Compare fine detail in the preview."/>}
        {advancedDLSS && <div className="form-grid"><Selector label="DLSS model preset" value={dlssPreset} onChange={v=>change('dlss_preset',v)} width="100%" options={presets.map(value=>({value,label:({default:'Automatic · recommended',j:'J · less ghosting, more flicker',k:'K · fine detail',l:'L · Ultra Performance default',m:'M · Performance default'})[value]}))} description="A model preference. NVIDIA may use a compatible preset instead."/><Selector label="Motion estimation" value={temporalQuality} onChange={v=>change('temporal_quality',v)} width="100%" options={['high','medium','low'].filter(v=>temporalQualities.includes(v)).map(value=>({value,label:({high:'High · most accurate',medium:'Balanced',low:'Fast · less accurate'})[value]}))} description="More accurate motion takes longer to process. Preview moving detail and scene cuts."/></div>}
        {generation && <div className="form-grid"><Selector label="Frame-generation mode" value={fgMode} onChange={v=>change('frame_generation_mode',v)} width="100%" options={(fgModes.length?fgModes:[fgMode]).map(value=>({value,label:frameModes[value]}))} isDisabled={!fgModes.length} description="Auto adds passes when needed. Native rejects rates beyond the hardware limit. Cascade uses repeated 2× passes."/><Selector label="Frame-generation motion" value={fgQuality} onChange={v=>change('frame_generation_quality',v)} width="100%" options={(fgQualities.length?fgQualities:[fgQuality]).map(value=>({value,label:motionNames[value]}))} isDisabled={!fgQualities.length} description="High takes longer. Check fast movement and scene cuts in the preview."/></div>}
        {hdr && <VStack gap={4}><Heading level={3}>HDR appearance</Heading><Copy type="supporting">Start with the defaults. Tune the preview before enhancing the full video.</Copy><div className="form-grid">{[['hdr_luminance','Peak brightness',400,2000,'nits','Match your HDR display. Default: 650 nits.'],['hdr_contrast','HDR contrast',0,200,null,'Lower softens contrast. Default: 100.'],['hdr_saturation','HDR saturation',0,200,null,'Lower reduces color intensity. Default: 100.'],['hdr_middle_gray','Midtone brightness',10,100,null,'Adjust overall brightness. Default: 50.']].map(([key,label,min,max,units,description])=><NumberInput key={key} label={label} value={desired[key]} onChange={v=>change(key,v)} min={min} max={max} step={1} units={units} isIntegerOnly isWheelEnabled={false} width="100%" description={description}/>)}</div><div className="checkbox-row"><CheckboxInput label="Reduce banding in HDR" value={desired.hdr_debanding} onChange={v=>change('hdr_debanding',v)}/></div></VStack>}
        <div className="form-grid"><Selector label="Encoding hardware" value={encoder} onChange={v=>change('encoder',v)} width="100%" options={['cpu','nvidia'].map(v=>({value:v,label:v==='cpu'?'CPU':'NVIDIA GPU',disabled:!encoders.includes(v)}))} description="Only verified encoders are available."/><Selector label="Export quality" value={desired.quality} onChange={v=>change('quality',v)} width="100%" options={[{value:'19',label:'High · larger file'},{value:'23',label:'Balanced'},{value:'28',label:'Compact · smaller file'}]} description="File size depends on the source and codec."/></div>
        <div className="form-grid">{[['denoise','Reduce noise'],['deinterlace','Deinterlace older video'],['sharpen','Light sharpening'],['interpolate','Smooth motion to 60 fps']].map(([key,label])=><div key={key} className="checkbox-row"><CheckboxInput label={label} value={engine==='resize' && desired[key]} onChange={v=>change(key,v)} isDisabled={engine!=='resize' || (key==='interpolate' && generation)}/></div>)}</div>
        <Copy type="supporting">Cleanup and 60 fps motion use conventional filters. Motion interpolation can be slow and changes the original cadence.</Copy>
      </VStack></Collapsible>
      {error && <Banner status="error" title={error} collapsible={false}/>}
      {engineUnavailable && <Banner status="warning" title="Selected enhancement is unavailable" description="Your settings are kept. Choose a compatible device or another enhancement." collapsible={false}/>}
      {!codecs.length && !engineUnavailable && <Copy type="supporting">{checking?'Your device is checking support. Processing becomes available when it is ready.':rulesEnabled?'Update or connect a worker that supports resolution rules in Devices & storage.':'Connect a compatible device in Devices & storage to start.'}</Copy>}
      <div className="recipe-actions"><Copy type="supporting">{path?`Selected: ${path.split('/').pop()}`:'Choose an input above.'}{path && engine!=='resize'?' · Experimental AI; compare a short preview first.':''}</Copy><HStack gap={3} wrap="wrap"><Button label="Preview 5 seconds" onClick={()=>submit(5)} isDisabled={!path || busy || !codecs.length || engineUnavailable || sizeInvalid || !desired.output_directory.trim()}/><Button label={paths.length>1?`Add ${paths.length} videos to queue`:'Add to queue'} type="submit" variant={review?'secondary':'primary'} isLoading={busy} isDisabled={!path || !codecs.length || engineUnavailable || sizeInvalid || !desired.output_directory.trim()}/></HStack></div>

    </VStack></form>
  </VStack></section></>;
}
function Workspace({state,onNotice,refresh,onAction}) {
  const [directory,setDirectory]=useState('.'),[offset,setOffset]=useState(0),[search,setSearch]=useState(''),[listing,setListing]=useState(null),[error,setError]=useState(''),[revision,setRevision]=useState(0),[selected,setSelected]=useState([]),[compareJob,setCompareJob]=useState(null);
  const libraries=state.storage.libraries || [{id:'default',name:'Your library',directory:'.'}];
  const library=libraries.find(item=>item.directory!=='.' && (directory===item.directory || directory.startsWith(item.directory+'/'))) || libraries[0];
  const relative=directory===library.directory?'':library.directory==='.'?directory:directory.slice(library.directory.length+1);
  const crumbs=relative.split('/').filter(Boolean);
  useEffect(()=>{let live=true;setListing(null);setError('');const timer=setTimeout(()=>api(`/api/library?directory=${encodeURIComponent(directory)}&offset=${offset}&search=${encodeURIComponent(search)}`).then(data=>{if(live)setListing(data);}).catch(e=>{if(live)setError(e.message);}),180);return()=>{live=false;clearTimeout(timer);};},[directory,offset,revision,search]);
  function folder(path){setDirectory(path);setOffset(0);setSearch('');}
  async function created(preview,clear=true,queuedPath=null){if(queuedPath)setSelected(current=>current.filter(p=>p!==queuedPath));if(clear){setSelected([]);setCompareJob(null);}await refresh();onNotice({text:preview?'Preview queued.':'Video queued. Your original is preserved.'});}
  return <VStack gap={6}>
    <div className="workspace-title"><Heading level={1}>Videos</Heading><Copy>Select videos, compare a frame, then queue your copies.</Copy></div>
    <div className="io-grid">
      <section className="panel io-pane" aria-label="Input"><HStack className="pane-heading" hAlign="between" gap={3}><Heading level={2}>Input</Heading><Button label="Refresh" variant="ghost" onClick={()=>setRevision(v=>v+1)}/></HStack>
        <VStack className="library-tools" gap={3}>
          <div className="library-fields">
          <Selector label="Library" value={library.directory} options={libraries.map(item=>({value:item.directory,label:item.name}))} onChange={folder} width="100%"/>
          <TextInput label="Filter this folder" value={search} onChange={value=>{setSearch(value);setOffset(0);}} placeholder="Movie, show or episode name" maxLength={120} width="100%"/>
          </div>
          <Copy type="supporting">Browse originals. Copies go to a separate output folder.</Copy>
        </VStack>
        <HStack className="folder-bar" hAlign="between" gap={2} wrap="wrap">
          <nav className="library-breadcrumbs" aria-label="Library folders"><Button label="All folders" variant="ghost" onClick={()=>folder(library.directory)} isDisabled={!crumbs.length}/>{crumbs.map((name,index)=><React.Fragment key={index}><Icon icon="chevronRight" size="sm" color="secondary"/>{index===crumbs.length-1?<Text type="supporting" className="path" aria-current="page">{name}</Text>:<Button label={name} variant="ghost" onClick={()=>folder([library.directory==='.'?'':library.directory,...crumbs.slice(0,index+1)].filter(Boolean).join('/'))}/>}</React.Fragment>)}</nav>
          {crumbs.length>0 && <Button label="Up a folder" variant="ghost" onClick={()=>folder(crumbs.length===1?library.directory:directory.split('/').slice(0,-1).join('/'))}/>}
        </HStack>
        <HStack className="library-selection" hAlign="between" gap={2} wrap="wrap"><Text type="supporting" color="secondary" role="status">{selected.length?`${selected.length} selected`:'Choose videos to test'}</Text><HStack gap={1}>{selected.length>0 && <Button label="Clear selection" variant="ghost" onClick={()=>{setSelected([]);setCompareJob(null);}}/>}{listing?.items.filter(item=>!item.directory).length>1 && <Button label={listing.items.filter(item=>!item.directory).every(item=>selected.includes(item.path))?'Clear page':'Select page'} variant="ghost" onClick={()=>{const files=listing.items.filter(item=>!item.directory).map(item=>item.path);setSelected(current=>files.every(file=>current.includes(file))?current.filter(file=>!files.includes(file)):[...new Set([...current,...files])]);}}/>}</HStack></HStack>
        <div className="pane-content">
          {error?<Empty title="Library unavailable" copy={error}/>:!listing?<Empty title="Loading your library…" copy="Reading your videos."/>:!listing.items.length?<Empty title={search?'No matches in this folder':'No videos here'} copy={search?'Try another name, or clear the filter to see all folders and videos.':'Choose another folder or library. Check its read-only mount in Devices & storage if videos are missing.'}/>:listing.items.map(item=><InputRow key={`${item.path}:${revision}`} item={item} selected={selected.includes(item.path)} onChoose={()=>item.directory?folder(item.path):setSelected(current=>current.includes(item.path)?current.filter(p=>p!==item.path):[...current,item.path])}/>)}
        </div>
        {listing?.total>100 && <HStack className="row" gap={3} hAlign="between" wrap="wrap"><Button label="Previous" variant="ghost" isDisabled={!offset} onClick={()=>setOffset(v=>Math.max(0,v-100))}/><Copy type="supporting">{offset+1}–{Math.min(offset+100,listing.total)} of {listing.total}</Copy><Button label="Next" variant="ghost" isDisabled={offset+100>=listing.total} onClick={()=>setOffset(v=>v+100)}/></HStack>}
      </section>
      <section className="panel io-pane" aria-label="Output queue"><HStack className="pane-heading" hAlign="between" gap={3}><Heading level={2}>Output queue</Heading><Text type="supporting" color="secondary">{state.jobs.length?`${state.jobs.length} ${state.jobs.length===1?'video':'videos'}`:'No jobs yet'}</Text></HStack><Jobs jobs={state.jobs} onAction={onAction} onCompare={job=>{setSelected(current=>current.includes(job.path)?current:[...current,job.path]);setCompareJob(job);}}/></section>
    </div>
    <Recipe paths={selected} state={state} onCreated={created} compareJob={compareJob}/>
  </VStack>;
}
function Processing({state,onAction,onNotice}) {
  const [pair,setPair]=useState(null), [copied,setCopied]=useState(false);
  async function connect(){try{const data=await api('/api/pair-codes',{method:'POST'});setPair(data.code);setCopied(false);}catch(e){onNotice({error:true,text:e.message});}}
  async function copy(){try{await navigator.clipboard.writeText(pair);setCopied(true);}catch{onNotice({text:'Select the pairing code and copy it manually. Automatic copying requires HTTPS or localhost.'});}}
  const workers=state.workers.filter(w=>!w.revoked);
  return <VStack gap={8}>
    <div><PageHead title="Your processing power" copy="Connect a computer on your network. It receives a copy, processes it locally, and returns the result." action={<Button label="Connect a worker" variant="primary" clickAction={connect}/>}/>
    {!workers.length?<section className="panel"><Empty title="Bring your processing power" copy="Connect your Spark, desktop or another computer. You can also run a worker beside this manager."/></section>:<div className="worker-layout">{workers.map(w=><article key={w.id} className="panel" aria-label={w.name}><VStack gap={5} padding={6}>
      <HStack gap={4} hAlign="between" wrap="wrap"><Heading level={2}>{w.name}</Heading><Status online={w.online && workerReady(w)?true:w.online && (w.capabilities.initialization==='checking' || w.capabilities.updates?.draining)?undefined:false}>{workerStatus(w)}</Status></HStack>
      <VStack gap={1}>{w.capabilities.device && <Copy>{w.capabilities.device}</Copy>}<Copy type="supporting">{w.capabilities.platform} / {w.capabilities.architecture}</Copy></VStack>
      {w.capabilities.initialization==='checking' && <Copy>Testing encoding and enhancements. This can take several minutes. Jobs wait until checks finish.</Copy>}
      {w.capabilities.initialization==='failed' && <Banner status="error" title="Support checks failed" description={w.capabilities.initialization_error || 'Restart the worker to run its support checks again.'} collapsible={false}/>}
      {workerReady(w) && <VStack gap={2}><Text weight="medium">Verified encoding</Text><Copy type="supporting">{(w.capabilities.encoders || []).map(c=>c.replace('_nvidia',' · NVIDIA').replace('_cpu',' · CPU').toUpperCase()).join(', ') || 'No verified encoder'}</Copy></VStack>}
      <VStack gap={2}><HStack gap={4} hAlign="between" wrap="wrap"><Text weight="medium">Temporary drive</Text><Text type="supporting">{w.scratch.available===false?'Unavailable':`${bytes(w.scratch.free_bytes || 0)} free`}</Text></HStack><Copy type="supporting" className="path">{w.scratch.path}</Copy></VStack>
      {workerReady(w) && <VStack gap={2}><Text weight="medium">Enhancement</Text><Copy type="supporting">{(w.capabilities.engines || []).map(e=>engines[e] || e).join(', ') || 'No verified engine'}</Copy></VStack>}
      {workerReady(w) && !!w.capabilities.dlss_frame_generation?.settings?.length && <VStack gap={2}><Text weight="medium">DLSS frame generation · experimental</Text><Copy type="supporting">Verified with {(w.capabilities.dlss_frame_generation.upscalers || []).map(e=>engines[e] || e).join(', ')}. Up to {w.capabilities.dlss_frame_generation.maximum_factor}× per NVIDIA pass.</Copy></VStack>}
      {workerReady(w) && !!w.capabilities.rtx_hdr?.pipelines?.length && <VStack gap={2}><Text weight="medium">RTX Video HDR · experimental</Text><Copy type="supporting">Verified 10-bit exports: {[...new Set(w.capabilities.rtx_hdr.pipelines.map(([, ,codec])=>codecNames[codec]))].join(', ')}. Available combinations appear in enhancement settings.</Copy></VStack>}
      {workerReady(w) && !!Object.keys(w.capabilities.notes || {}).length && <Collapsible trigger="Unavailable engine details" defaultIsOpen={false}><VStack gap={3} paddingBlockStart={3}>{Object.entries(w.capabilities.notes).map(([engine,text])=><Copy key={engine} type="supporting">{engines[engine] || engine}: {text}</Copy>)}</VStack></Collapsible>}
      {w.capabilities.updates?.version && <VStack gap={2}><Text weight="medium">Worker {w.capabilities.updates.version}</Text>{w.capabilities.updates.enabled || w.capabilities.updates.state?<><Copy type="supporting" role="status" aria-label="Worker update">{w.update_pending?'Update requested. Your current job can finish.':updateCopy[w.capabilities.updates.state] || 'Ready to check for an update.'} {w.capabilities.updates.automatic?'New releases are checked automatically.':''}</Copy><Button variant="secondary" label="Check for updates" disabled={!w.online || !w.capabilities.updates.enabled || !!w.update_pending || ['checking','waiting','installing','validating'].includes(w.capabilities.updates.state)} clickAction={()=>onAction(w.id,'update')}/></>:<Copy type="supporting">Updates are managed on the processing computer.</Copy>}</VStack>}
      <Button variant="ghost" label="Disconnect worker" clickAction={()=>onAction(w.id,'revoke')}/>
    </VStack></article>)}</div>}</div>
    {pair && <section className="panel" aria-label="Pairing instructions"><VStack gap={5} padding={6}>
      <HStack gap={4} hAlign="between"><Heading level={2}>Connect your worker</Heading><Button label="Close" variant="ghost" onClick={()=>setPair(null)}/></HStack>
      <Copy>This code expires in 10 minutes and can be used once.</Copy>
      <div className="pair-code"><Text type="code" id="pair-code">{pair}</Text></div><Button label={copied?'Copied':'Copy pairing code'} clickAction={copy}/>
      <VStack gap={5}>
        <VStack gap={2}><Heading level={3}>1. On the processing computer</Heading><Copy>Install the worker using the Docker worker example. Set the manager address to <strong>{location.origin}</strong> and enter this pairing code.</Copy></VStack>
        <VStack gap={2}><Heading level={3}>2. Choose its temporary drive</Heading><Copy>Mount your Optane or another drive as the scratch folder. Mark the mounted folder with <code>init-scratch</code>. The worker will stop if that folder is unavailable.</Copy></VStack>
        <VStack gap={2}><Heading level={3}>3. Check the connection</Heading><Copy>The device appears as soon as it pairs. Support checks can take several minutes; verified options appear when complete. Use Ethernet for large libraries; Wi-Fi works when both devices can reach each other.</Copy></VStack>
      </VStack>
      <Button variant="ghost" label="Open installation guide" href="https://github.com/thekozugroup/Popcorn-SR/blob/main/docs/deployment.md" target="_blank" rel="noreferrer"/>
    </VStack></section>}
    <VStack gap={6} className="footnote"><VStack gap={2}><Heading level={3}>Use what your device actually supports</Heading><Copy>Encoding and AI engines appear after a real processing check. Real-ESRGAN supports Linux NVIDIA workers. RTX Video and DLSS need a separately installed, compatible processing engine.</Copy></VStack><VStack gap={2}><Heading level={3}>One device works too</Heading><Copy>Run the manager and worker together. Your library and scratch drive remain separate, even when they live on the same computer.</Copy></VStack></VStack>
  </VStack>;
}
function Settings({state,account,onLogout,onPasskey,onSaved}) {
  const sections=[
    ['Library',`${(state.storage.libraries || [{name:'Your library'}]).map(item=>item.name).join(', ')}. Choose a library in Input, then open its folders and select videos. Add library folders as read-only Docker mounts; see the library guide.`],
    ['Finished copies',`${state.storage.output} / ${bytes(state.storage.free_bytes)} available. Choose a subfolder when creating a job. Originals are never replaced.`],
    ['Temporary storage',"Each worker owns its scratch drive. Video downloads, intermediates and uploads use that drive; small pairing credentials use its state folder. Check the host’s swap and Docker storage configuration to keep those writes off the built-in drive too."],
    ['Network','Direct Ethernet or a shared router/switch works. A plain USB-C cable does not establish a network between ordinary host ports. Wi-Fi works, with transfer speed and reliability depending on your network.'],
    ['Protected sources','This release rejects HDR and high-bit-depth input to prevent loss of color or detail. Keep your original and use a verified HDR pipeline for those files.'],
    ['Access','Keep the manager on your trusted network. Use HTTPS through a reverse proxy or VPN for remote access.'],
  ];
  return <><PageHead title="Your workspace" copy="A small manager, connected processing, and a separate home for every finished copy."/><section className="panel">{sections.map(([title,copy])=><VStack className="row" key={title} gap={3}><Heading level={2}>{title}</Heading><Copy>{copy}</Copy>{title==='Library' && <Button label="Library guide" variant="ghost" href="https://github.com/thekozugroup/Popcorn-SR/blob/main/docs/library.md" target="_blank" rel="noreferrer"/>}{title==='Access' && <VStack gap={4}><Text>Signed in as {account.username}</Text><Button label="Add a passkey" variant="secondary" onClick={onPasskey}/><Collapsible trigger="Change password"><PasswordForm account={account} onSaved={onSaved}/></Collapsible><Button label="Sign out" variant="ghost" onClick={onLogout}/></VStack>}</VStack>)}</section></>;
}
function App() {
  const [account,setAccount]=useState(null),[state,setState]=useState(null),[loading,setLoading]=useState(true),[loginError,setLoginError]=useState(''),[view,setView]=useState('workspace'),[notice,setNotice]=useState(null),[interrupted,setInterrupted]=useState(false);
  const refreshing=useRef(false), surface=useRef(null);
  const expired=()=>{setState(null);setAccount(previous=>({...previous,authenticated:false}));setView('workspace');setNotice(null);};
  async function refresh(){
    if(refreshing.current)return;
    refreshing.current=true;
    try{const session=await api('/api/auth/session');setAccount(session);if(!session.authenticated || session.must_change_password || session.offer_passkey){setState(null);return;}const data=await api('/api/state');setState(data);setInterrupted(false);setLoginError('');}
    catch(e){if(state){setInterrupted(true);}else if(!e.message.includes('Sign in'))setLoginError(e.message);}
    finally{refreshing.current=false;setLoading(false);}
  }
  useEffect(()=>{refresh();window.addEventListener('session-expired',expired);return()=>window.removeEventListener('session-expired',expired);},[]);
  useEffect(()=>{if(!state)return;const poll=()=>{if(!document.hidden)refresh();};const interval=setInterval(poll,3000);document.addEventListener('visibilitychange',poll);return()=>{clearInterval(interval);document.removeEventListener('visibilitychange',poll);};},[!!state]);
  function navigate(next){setView(next);setNotice(null);}
  useEffect(()=>{surface.current?.focus({preventScroll:true});},[view]);
  async function onAction(id,action){
    try{await api(['revoke','update'].includes(action)?`/api/workers/${id}/${action}`:`/api/jobs/${id}/${action}`,{method:'POST'});await refresh();if(action==='full')setNotice({text:'Full video queued using your preview settings. Your original is preserved.'});if(action==='update')setNotice({text:'Update check requested. The current job finishes before this device restarts.'});}
    catch(e){setNotice({error:true,text:e.message});}
  }
  async function logout(){try{await api('/api/logout',{method:'POST'});expired();}catch(e){setNotice({error:true,text:e.message});}}
  if(loading)return <div className="login-wrap"><Text>Opening Popcorn SR…</Text></div>;
  if(!state || account?.offer_passkey)return <Login key={String(account?.authenticated)+String(account?.must_change_password)+String(account?.offer_passkey)} account={account} onLogin={refresh} initialError={loginError}/>;
  const workers=state.workers.filter(w=>!w.revoked);
  const connected=workers.filter(w=>w.online);
  const connection=interrupted?'Connection interrupted':connected.length===1?`${connected[0].name} · Connected`:connected.length?`${connected.length} devices connected`:workers.length?'Device offline':'No processing device';
  const connectionTone=interrupted?'warning':connected.length?'success':'neutral';
  return <><a className="skip-link" href="#workspace">Skip to workspace</a><header className="app-header"><div className="header-inner"><Brand/><div className="header-actions"><Badge id="connection" className="connection-chip" variant={connectionTone} label={connection} icon={<span className={`status-dot ${connectionTone==='success'?'online':connectionTone==='warning'?'warning':''}`} aria-hidden="true"/>}/><Button label={view==='workspace'?'Devices & storage':'Back to videos'} variant="ghost" onClick={()=>navigate(view==='workspace'?'setup':'workspace')}/></div></div></header>
    <main className="workspace" id="workspace" ref={surface} tabIndex={-1}><VStack gap={6}>
      <Feedback message={notice}/>
      {interrupted && <Banner status="warning" title="Connection interrupted" description="Reconnecting automatically. Your saved jobs remain on the manager." collapsible={false}/>}
      <div hidden={view!=='workspace'}><Workspace state={state} refresh={refresh} onNotice={setNotice} onAction={onAction}/></div>
      {view==='setup' && <><Processing state={state} onAction={onAction} onNotice={setNotice}/><Collapsible trigger="Storage & help" defaultIsOpen={false}><Settings state={state} account={account} onLogout={logout} onPasskey={()=>{setState(null);setAccount(previous=>({...previous,offer_passkey:true}));}} onSaved={refresh}/></Collapsible></>}
    </VStack></main></>;

}
createRoot(document.getElementById('root')).render(<Theme theme={popcornTheme} mode="system"><App/></Theme>);

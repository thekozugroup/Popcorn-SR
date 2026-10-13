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
import {popcornTheme} from './themes/popcorn.js';
import './styles.css';

const engines = {resize: 'Conventional resizing', realesrgan: 'Real-ESRGAN AI upscaling', 'rtx-vsr': 'RTX Video Super Resolution', 'dlss-sr': 'DLSS video upscaling · experimental', dlss5: 'DLSS 5 neural rendering · experimental'};
const dlssModes = {dlaa:'DLAA · keep source size',quality:'Quality · 1.5×',balanced:'Balanced · about 1.72×',performance:'Performance · 2×','ultra-performance':'Ultra Performance · 3×'};
const codecNames = {h264:'H.264',hevc:'H.265 / HEVC',av1:'AV1'};
const vsrLevels = {'1':'Level 1 · Fast','2':'Level 2 · Balanced','3':'Level 3 · High','4':'Level 4 · Ultra'};
const frameRates = ['23.976','25','29.97','30','50','59.94','60','90','119.88','120','144','165','180','240','360','480'];
const frameModes = {auto:'Auto · recommended',native:'Native · one NVIDIA pass',cascade:'Cascade · multiple NVIDIA passes'};
const motionNames = {high:'High',medium:'Balanced',low:'Fast'};
const bytes = n => n >= 1024 ** 3 ? `${(n / 1024 ** 3).toFixed(1)} GB` : `${(n / 1024 ** 2).toFixed(1)} MB`;
const workerReady = w => w.capabilities.initialization===undefined || w.capabilities.initialization==='ready';
const workerStatus = w => !w.online?'Offline':w.capabilities.initialization==='checking'?'Checking support':workerReady(w)?'Connected':'Checks failed';
async function api(path, options = {}) {
  const response = await fetch(path, {credentials: 'same-origin', ...options, headers: {'Content-Type':'application/json', ...options.headers}});
  const data = await response.json().catch(() => ({detail:'The manager returned an unexpected response.'}));
  if (!response.ok) {
    if (response.status === 401 && path !== '/api/login') window.dispatchEvent(new Event('session-expired'));
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
    <Brand/>
    <VStack gap={3}><Heading level={1}>Your library, improved.</Heading><Copy>Sign in to connect your library and processing devices.</Copy></VStack>
    <form onSubmit={submit}><VStack gap={5}>
      <TextInput label="Access key" type="password" value={key} onChange={value=>setKey(value)} autoComplete="current-password" isRequired description="Use the key generated during installation."/>
      {error && <Banner status="error" title={error} collapsible={false}/>}
      <Button label="Open Popcorn SR" type="submit" variant="primary" isLoading={busy} isDisabled={!key}/>
    </VStack></form>
    <Copy type="supporting">Self-hosted. Your videos stay on your devices.</Copy>
  </VStack></main></div>;
}
function Jobs({jobs,onAction}) {
  return <div id="jobs" className="pane-content" aria-label="Output jobs">
    {!jobs.length ? <Empty title="Finished copies appear here" copy="Choose an input, then add it to the queue."/> : jobs.map(job => <article className="row job-row" key={job.id} data-job-id={job.id} aria-label={job.path.split('/').pop()}>
      <HStack gap={3} hAlign="between" vAlign="start"><Text weight="semibold" className="path">{job.path.split('/').pop()}{job.recipe.preview_seconds ? ' · Preview' : ''}</Text><Text type="supporting" className="job-status">{({completed:'Ready',failed:'Failed',cancelled:'Cancelled',queued:'Queued',running:`${Math.floor(job.progress)}%`})[job.status] || job.status}</Text></HStack>
      <Copy type="supporting">{job.stage}{job.status==='queued'?' · Waiting for a compatible device':''}</Copy>
      {job.status==='running' && <ProgressBar label={`Processing ${job.path}`} value={job.progress} isLabelHidden/>}
      {job.error && <Banner status="error" title={job.error} collapsible={false}/>}
      <HStack gap={2} wrap="wrap">
        {job.status==='completed'?<><Button href={`/api/jobs/${job.id}/download`} label={`Download ${job.recipe.preview_seconds?'preview':'copy'}`}/>{!!job.recipe.preview_seconds && <Button label="Enhance full video" clickAction={()=>onAction(job.id,'full')}/>}</>:['failed','cancelled'].includes(job.status)?<Button label="Retry" clickAction={()=>onAction(job.id,'retry')}/>:<Button variant="ghost" label="Cancel" clickAction={()=>onAction(job.id,'cancel')}/>}
        <Collapsible trigger="Details" defaultIsOpen={false}><VStack gap={2} paddingBlockStart={2}>
          <Copy type="supporting">{engines[job.recipe.engine] || job.recipe.engine} · {codecNames[job.recipe.codec] || job.recipe.codec} / {job.recipe.output_width?`${job.recipe.output_width} × ${job.recipe.output_height} px`:job.recipe.engine==='dlss-sr' && job.recipe.dlss_mode?dlssModes[job.recipe.dlss_mode]:`${job.recipe.scale}×`}</Copy>
          {job.recipe.engine==='rtx-vsr' && <Copy type="supporting">VSR quality: {job.recipe.vsr_quality?vsrLevels[job.recipe.vsr_quality]:'Worker default'}{job.recipe.vsr_strength!=null?` · Strength: ${Math.round(job.recipe.vsr_strength*100)}%`:''}</Copy>}
          {job.recipe.engine==='dlss-sr' && <Copy type="supporting">Preset: {job.recipe.dlss_preset && job.recipe.dlss_preset!=='default'?job.recipe.dlss_preset.toUpperCase():'Automatic'} · Motion estimation: {motionNames[job.recipe.temporal_quality || 'high']}</Copy>}
          {job.recipe.frame_generation && <Copy type="supporting">DLSS frame generation: {job.recipe.frame_rate} fps · {frameModes[job.recipe.frame_generation_mode || 'auto'].split(' · ')[0]} · Motion: {motionNames[job.recipe.frame_generation_quality || 'high']}</Copy>}
          {job.recipe.hdr && <Copy type="supporting">RTX Video HDR · 10-bit · Peak brightness: {job.recipe.hdr_luminance || 650} nits</Copy>}
          {job.result && <Copy type="supporting" className="path">{job.result.path} / {bytes(job.result.bytes)}</Copy>}
        </VStack></Collapsible>
      </HStack>
    </article>)}
  </div>;
}
function Recipe({path,state,onCreated}) {
  const [desired,setDesired]=useState({worker:'',engine:'auto',scale:'2',size_mode:'scale',output_width:1920,output_height:1080,vsr_quality:'default',vsr_strength:null,codec:'h264',encoder:'auto',quality:'23',dlss_mode:'performance',dlss_preset:'default',temporal_quality:'high',frame_generation:false,frame_rate:'60',frame_generation_mode:'auto',frame_generation_quality:'high',hdr:false,hdr_contrast:100,hdr_saturation:100,hdr_middle_gray:50,hdr_luminance:650,hdr_debanding:true,output_directory:'enhanced',denoise:false,deinterlace:false,sharpen:false,interpolate:false});
  const [error,setError]=useState(''), [busy,setBusy]=useState(false);
  const active=state.workers.filter(w=>!w.revoked);
  const worker=active.some(w=>w.id===desired.worker)?desired.worker:'';
  const selected=active.filter(w=>!worker || w.id===worker);
  const candidates=selected.filter(workerReady);
  const checking=selected.some(w=>w.capabilities.initialization==='checking');
  const failed=selected.some(w=>w.capabilities.initialization==='failed');
  const supported=[...new Set(candidates.flatMap(w=>w.capabilities.engines || []))];
  const engine=desired.engine==='auto'?['dlss-sr','rtx-vsr','realesrgan','resize'].find(e=>supported.includes(e)) || 'resize':desired.engine;
  const engineUnavailable=desired.engine!=='auto' && !supported.includes(desired.engine);
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
  async function submit(preview_seconds) {
    if(!path || busy || engineUnavailable || !codecs.length || !desired.output_directory.trim()) return;
    if(vsrUnavailable || sizeInvalid) { setError('Choose verified RTX Video settings and dimensions that are multiples of 8.'); return; }
    if(generation && !fgModes.length) { setError('DLSS frame generation is unavailable. Choose a compatible worker or turn off frame generation.'); return; }
    if(hdr && !hdrWorkers.length) { setError('RTX Video HDR is unavailable. Choose a compatible worker or turn off HDR.'); return; }
    setBusy(true); setError('');
    const recipe={engine,scale:Number(scale),codec,encoder,quality:Number(desired.quality),output_directory:desired.output_directory,preview_seconds};
    if(advancedDLSS) Object.assign(recipe,{dlss_mode:dlssMode,dlss_preset:dlssPreset,temporal_quality:temporalQuality});
    if(vsr && desired.vsr_quality!=='default') recipe.vsr_quality=Number(desired.vsr_quality);
    if(vsr && desired.vsr_strength!==null) recipe.vsr_strength=desired.vsr_strength/100;
    if(customSize) Object.assign(recipe,{output_width:desired.output_width,output_height:desired.output_height});
    if(generation) Object.assign(recipe,{frame_generation:true,frame_rate:desired.frame_rate,frame_generation_mode:fgMode,frame_generation_quality:fgQuality});
    if(hdr) Object.assign(recipe,{hdr:true,...Object.fromEntries(['hdr_contrast','hdr_saturation','hdr_middle_gray','hdr_luminance','hdr_debanding'].map(key=>[key,desired[key]]))});
    for(const key of ['denoise','deinterlace','sharpen','interpolate']) recipe[key]=engine==='resize' && desired[key];
    if(generation) recipe.interpolate=false;
    try { await api('/api/jobs',{method:'POST',body:JSON.stringify({path,recipe,worker_id:worker || null})}); await onCreated(preview_seconds); }
    catch(e){setError(e.message);}
    finally{setBusy(false);}
  }
  return <section className="recipe" aria-label="Upscaling settings"><VStack gap={5}>
    <Heading level={2}>Upscaling settings</Heading>
    <form onSubmit={e=>{e.preventDefault();submit(0);}}><VStack gap={6}>
      <div className="settings-grid">
        <Selector label="Enhancement" value={engine} onChange={v=>change('engine',v)} width="100%" options={[...new Set([...supported,engine])].map(e=>({value:e,label:engines[e] || e,disabled:!supported.includes(e)}))}/>
        {advancedDLSS?<Selector label="DLSS mode" value={dlssMode} onChange={v=>change('dlss_mode',v)} width="100%" options={modes.map(value=>({value,label:dlssModes[value]}))}/>:<Selector label="Output size" value={customSize?'custom':scale} onChange={v=>v==='custom'?change('size_mode','custom'):setDesired(current=>({...current,size_mode:'scale',scale:v}))} width="100%" options={[...scales.map(v=>({value:v,label:({'1':'Keep source size (1×)','2':'Twice the size (2×)','3':'Three times the size (3×)','4':'Four times the size (4×)'})[v]})),...(vsr && capable.some(w=>w.capabilities.rtx_vsr?.custom_size) || customSize?[{value:'custom',label:'Custom dimensions'}]:[])]}/>}
        <Selector label="Video format" value={codec} onChange={v=>change('codec',v)} width="100%" options={['h264','hevc','av1'].map(v=>({value:v,label:({h264:'H.264 · broad compatibility',hevc:'H.265 / HEVC · smaller files',av1:'AV1 · newer players'})[v],disabled:!codecs.includes(v)}))}/>
      </div>
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
      {!codecs.length && !engineUnavailable && <Copy type="supporting">{checking?'Your device is checking support. Processing becomes available when it is ready.':'Connect a compatible device in Devices & storage to start.'}</Copy>}
      <div className="recipe-actions"><Copy type="supporting">{path?`Selected: ${path.split('/').pop()}`:'Choose an input above.'}{path && engine!=='resize'?' · Experimental AI; compare a short preview first.':''}</Copy><HStack gap={3} wrap="wrap"><Button label="Preview 5 seconds" onClick={()=>submit(5)} isDisabled={!path || busy || !codecs.length || engineUnavailable || sizeInvalid || !desired.output_directory.trim()}/><Button label="Add to queue" type="submit" variant="primary" isLoading={busy} isDisabled={!path || !codecs.length || engineUnavailable || sizeInvalid || !desired.output_directory.trim()}/></HStack></div>

    </VStack></form>
  </VStack></section>;
}
function Workspace({state,onNotice,refresh,onAction}) {
  const [directory,setDirectory]=useState('.'),[offset,setOffset]=useState(0),[listing,setListing]=useState(null),[error,setError]=useState(''),[revision,setRevision]=useState(0),[selected,setSelected]=useState(null);
  useEffect(()=>{let live=true;setListing(null);setError('');api(`/api/library?directory=${encodeURIComponent(directory)}&offset=${offset}`).then(data=>{if(live)setListing(data);}).catch(e=>{if(live)setError(e.message);});return()=>{live=false;};},[directory,offset,revision]);
  function folder(path){setDirectory(path);setOffset(0);setSelected(null);}
  async function created(preview){setSelected(null);await refresh();onNotice({text:preview?'Preview queued.':'Video queued. Your original is preserved.'});}
  return <VStack gap={8}>
    <div><Heading level={1}>Upscale your videos</Heading><Copy>Choose an input. Make a better copy. Keep the original.</Copy></div>
    <div className="io-grid">
      <section className="panel io-pane" aria-label="Input"><HStack className="pane-heading" hAlign="between" gap={3}><Heading level={2}>Input</Heading><Button label="Refresh" variant="ghost" onClick={()=>setRevision(v=>v+1)}/></HStack>
        <HStack className="folder-bar" hAlign="between" gap={3} wrap="wrap"><Text type="supporting" color="secondary" className="path min-w-0">{directory==='.'?'Your library':directory}</Text>{directory!=='.' && <Button label="Up a folder" variant="ghost" onClick={()=>folder(directory.split('/').slice(0,-1).join('/') || '.')}/>}</HStack>
        <div className="pane-content">
          {error?<Empty title="Library unavailable" copy={error}/>:!listing?<Empty title="Loading your library…" copy="Reading your videos."/>:!listing.items.length?<Empty title="No videos here" copy="Choose another folder, or check your library mount in Devices & storage."/>:listing.items.map(item=><div className={`row file-row ${selected===item.path?'selected-file':''}`} key={item.path}><Button label={item.name} variant="ghost" aria-pressed={!item.directory?selected===item.path:undefined} onClick={()=>item.directory?folder(item.path):setSelected(selected===item.path?null:item.path)}><VStack gap={1} hAlign="start" className="min-w-0"><Text weight="medium" className="path">{item.name}</Text><Copy type="supporting">{item.directory?'Open folder':bytes(item.size)}</Copy></VStack></Button>{selected===item.path && <Text type="supporting">Selected</Text>}</div>)}
        </div>
        {listing?.total>100 && <HStack className="row" gap={3} hAlign="between" wrap="wrap"><Button label="Previous" variant="ghost" isDisabled={!offset} onClick={()=>setOffset(v=>Math.max(0,v-100))}/><Copy type="supporting">{offset+1}–{Math.min(offset+100,listing.total)} of {listing.total}</Copy><Button label="Next" variant="ghost" isDisabled={offset+100>=listing.total} onClick={()=>setOffset(v=>v+100)}/></HStack>}
      </section>
      <section className="panel io-pane" aria-label="Output queue"><HStack className="pane-heading" hAlign="between" gap={3}><Heading level={2}>Output queue</Heading><Text type="supporting" color="secondary">{state.jobs.length?`${state.jobs.length} ${state.jobs.length===1?'video':'videos'}`:'No jobs yet'}</Text></HStack><Jobs jobs={state.jobs} onAction={onAction}/></section>
    </div>
    <Recipe path={selected} state={state} onCreated={created}/>
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
      <HStack gap={4} hAlign="between" wrap="wrap"><Heading level={2}>{w.name}</Heading><Status online={w.online && workerReady(w)?true:w.online && w.capabilities.initialization==='checking'?undefined:false}>{workerStatus(w)}</Status></HStack>
      <VStack gap={1}>{w.capabilities.device && <Copy>{w.capabilities.device}</Copy>}<Copy type="supporting">{w.capabilities.platform} / {w.capabilities.architecture}</Copy></VStack>
      {w.capabilities.initialization==='checking' && <Copy>Testing encoding and enhancements. This can take several minutes. Jobs wait until checks finish.</Copy>}
      {w.capabilities.initialization==='failed' && <Banner status="error" title="Support checks failed" description={w.capabilities.initialization_error || 'Restart the worker to run its support checks again.'} collapsible={false}/>}
      {workerReady(w) && <VStack gap={2}><Text weight="medium">Verified encoding</Text><Copy type="supporting">{(w.capabilities.encoders || []).map(c=>c.replace('_nvidia',' · NVIDIA').replace('_cpu',' · CPU').toUpperCase()).join(', ') || 'No verified encoder'}</Copy></VStack>}
      <VStack gap={2}><HStack gap={4} hAlign="between" wrap="wrap"><Text weight="medium">Temporary drive</Text><Text type="supporting">{w.scratch.available===false?'Unavailable':`${bytes(w.scratch.free_bytes || 0)} free`}</Text></HStack><Copy type="supporting" className="path">{w.scratch.path}</Copy></VStack>
      {workerReady(w) && <VStack gap={2}><Text weight="medium">Enhancement</Text><Copy type="supporting">{(w.capabilities.engines || []).map(e=>engines[e] || e).join(', ') || 'No verified engine'}</Copy></VStack>}
      {workerReady(w) && !!w.capabilities.dlss_frame_generation?.settings?.length && <VStack gap={2}><Text weight="medium">DLSS frame generation · experimental</Text><Copy type="supporting">Verified with {(w.capabilities.dlss_frame_generation.upscalers || []).map(e=>engines[e] || e).join(', ')}. Up to {w.capabilities.dlss_frame_generation.maximum_factor}× per NVIDIA pass.</Copy></VStack>}
      {workerReady(w) && !!w.capabilities.rtx_hdr?.pipelines?.length && <VStack gap={2}><Text weight="medium">RTX Video HDR · experimental</Text><Copy type="supporting">Verified 10-bit exports: {[...new Set(w.capabilities.rtx_hdr.pipelines.map(([, ,codec])=>codecNames[codec]))].join(', ')}. Available combinations appear in enhancement settings.</Copy></VStack>}
      {workerReady(w) && !!Object.keys(w.capabilities.notes || {}).length && <Collapsible trigger="Unavailable engine details" defaultIsOpen={false}><VStack gap={3} paddingBlockStart={3}>{Object.entries(w.capabilities.notes).map(([engine,text])=><Copy key={engine} type="supporting">{engines[engine] || engine}: {text}</Copy>)}</VStack></Collapsible>}
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
  const [state,setState]=useState(null),[loading,setLoading]=useState(true),[loginError,setLoginError]=useState(''),[view,setView]=useState('workspace'),[notice,setNotice]=useState(null),[interrupted,setInterrupted]=useState(false);
  const refreshing=useRef(false), surface=useRef(null);
  const expired=()=>{setState(null);setView('workspace');setNotice(null);};
  async function refresh(){
    if(refreshing.current)return;
    refreshing.current=true;
    try{const data=await api('/api/state');setState(data);setInterrupted(false);setLoginError('');}
    catch(e){if(state){setInterrupted(true);}else if(!e.message.includes('Sign in'))setLoginError(e.message);}
    finally{refreshing.current=false;setLoading(false);}
  }
  useEffect(()=>{refresh();window.addEventListener('session-expired',expired);return()=>window.removeEventListener('session-expired',expired);},[]);
  useEffect(()=>{if(!state)return;const poll=()=>{if(!document.hidden)refresh();};const interval=setInterval(poll,3000);document.addEventListener('visibilitychange',poll);return()=>{clearInterval(interval);document.removeEventListener('visibilitychange',poll);};},[!!state]);
  function navigate(next){setView(next);setNotice(null);}
  useEffect(()=>{surface.current?.focus({preventScroll:true});},[view]);
  async function onAction(id,action){
    try{await api(action==='revoke'?`/api/workers/${id}/revoke`:`/api/jobs/${id}/${action}`,{method:'POST'});await refresh();if(action==='full')setNotice({text:'Full video queued using your preview settings. Your original is preserved.'});}
    catch(e){setNotice({error:true,text:e.message});}
  }
  async function logout(){try{await api('/api/logout',{method:'POST'});expired();}catch(e){setNotice({error:true,text:e.message});}}
  if(loading)return <div className="login-wrap"><Text>Opening Popcorn SR…</Text></div>;
  if(!state)return <Login key={loginError} onLogin={refresh} initialError={loginError}/>;
  const workers=state.workers.filter(w=>!w.revoked);
  const ready=workers.filter(w=>w.online && workerReady(w));
  const checking=workers.some(w=>w.online && w.capabilities.initialization==='checking');
  const connection=interrupted?'Connection interrupted':ready.length===1?`${ready[0].name} · Connected`:ready.length?`${ready.length} devices connected`:checking?'Checking support':workers.length?'Device offline':'No processing device';
  return <><a className="skip-link" href="#workspace">Skip to workspace</a><header className="app-header"><div className="header-inner"><Brand/><HStack gap={4} wrap="wrap" hAlign="end"><Status id="connection" online={interrupted?false:ready.length?true:undefined}>{connection}</Status><Button label={view==='workspace'?'Devices & storage':'Back to videos'} variant="ghost" onClick={()=>navigate(view==='workspace'?'setup':'workspace')}/></HStack></div></header>
    <main className="workspace" id="workspace" ref={surface} tabIndex={-1}><VStack gap={6}>
      <Feedback message={notice}/>
      {interrupted && <Banner status="warning" title="Connection interrupted" description="Reconnecting automatically. Your saved jobs remain on the manager." collapsible={false}/>}
      <div hidden={view!=='workspace'}><Workspace state={state} refresh={refresh} onNotice={setNotice} onAction={onAction}/></div>
      {view==='setup' && <><Processing state={state} onAction={onAction} onNotice={setNotice}/><Collapsible trigger="Storage & help" defaultIsOpen={false}><Settings state={state} onLogout={logout}/></Collapsible></>}
    </VStack></main></>;

}
createRoot(document.getElementById('root')).render(<Theme theme={popcornTheme} mode="system"><App/></Theme>);

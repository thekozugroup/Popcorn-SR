import React, {useEffect, useRef, useState} from 'react';
import {HStack} from '@astryxdesign/core/HStack';
import {Text} from '@astryxdesign/core/Text';
import {Button} from '@astryxdesign/core/Button';

// Share a position in picture coordinates, not output pixels: unequal resolutions
// and letterboxed frames must still reveal the same part of the picture.
export function FrameComparison({frames, description, onLoad, onError}) {
  const panes=useRef([]), pictures=useRef([]);
  const view=useRef({zoom:1,x:.5,y:.5}), drag=useRef(null), scheduled=useRef(null);
  const [zoom,setZoom]=useState(1), [available,setAvailable]=useState(false);
  const geometry=index=>{
    const pane=panes.current[index], image=pictures.current[index];
    if(!pane || !image?.naturalWidth)return null;
    const width=pane.clientWidth, height=pane.clientHeight;
    const fit=Math.min(width/image.naturalWidth,height/image.naturalHeight);
    return {width,height,pictureWidth:image.naturalWidth*fit,pictureHeight:image.naturalHeight*fit};
  };
  function paint() {
    scheduled.current=null;
    const current=view.current;
    let minX=0, maxX=1, minY=0, maxY=1;
    panes.current.forEach((pane,index)=>{
      const g=geometry(index);if(!g)return;
      const x=Math.min(.5,g.width/(2*g.pictureWidth*current.zoom));
      const y=Math.min(.5,g.height/(2*g.pictureHeight*current.zoom));
      minX=Math.max(minX,x);maxX=Math.min(maxX,1-x);
      minY=Math.max(minY,y);maxY=Math.min(maxY,1-y);
    });
    current.x=Math.max(minX,Math.min(maxX,current.x));
    current.y=Math.max(minY,Math.min(maxY,current.y));
    panes.current.forEach((pane,index)=>{
      if(!pane)return;
      pane.dataset.zoomed=String(current.zoom>1);
      const g=geometry(index);if(!g)return;
      const image=pictures.current[index];
      // CSS property assignment keeps the existing strict stylesheet CSP intact.
      image.style.transform=`translate(${(.5-current.x)*g.pictureWidth*current.zoom}px, ${(.5-current.y)*g.pictureHeight*current.zoom}px) scale(${current.zoom})`;
    });
  }
  function schedule() {if(scheduled.current===null)scheduled.current=requestAnimationFrame(paint);}
  function changeZoom(value,index,point) {
    const current=view.current, next=Math.max(1,Math.min(8,value)), g=geometry(index);
    if(g && point) {
      const rect=panes.current[index].getBoundingClientRect();
      const dx=point.x-rect.left-g.width/2, dy=point.y-rect.top-g.height/2;
      current.x+=dx/g.pictureWidth*(1/current.zoom-1/next);
      current.y+=dy/g.pictureHeight*(1/current.zoom-1/next);
    }
    current.zoom=next;
    if(next===1){current.x=.5;current.y=.5;}
    setZoom(next);schedule();
  }
  function release(event) {
    if(drag.current?.id!==event.pointerId)return;
    drag.current=null;delete event.currentTarget.dataset.dragging;
  }
  function keyDown(event,index) {
    if(event.key==='+' || event.key==='=')changeZoom(view.current.zoom*2);
    else if(event.key==='-')changeZoom(view.current.zoom/2);
    else if(event.key==='0' || event.key==='Home')changeZoom(1);
    else if(event.key.startsWith('Arrow') && view.current.zoom>1) {
      const g=geometry(index);if(!g)return;
      const {zoom}=view.current;
      if(event.key==='ArrowLeft')view.current.x-=g.width*.1/(g.pictureWidth*zoom);
      if(event.key==='ArrowRight')view.current.x+=g.width*.1/(g.pictureWidth*zoom);
      if(event.key==='ArrowUp')view.current.y-=g.height*.1/(g.pictureHeight*zoom);
      if(event.key==='ArrowDown')view.current.y+=g.height*.1/(g.pictureHeight*zoom);
      schedule();
    } else return;
    event.preventDefault();
  }
  useEffect(()=>{
    const observer=new ResizeObserver(schedule);
    const listeners=panes.current.map((pane,index)=>{
      observer.observe(pane);
      const wheel=event=>{
        if(!geometry(index) || (!event.ctrlKey && !event.metaKey && view.current.zoom===1))return;
        if(!event.deltaY)return;
        event.preventDefault();
        const delta=event.deltaY*(event.deltaMode===1?16:event.deltaMode===2?pane.clientHeight:1);
        changeZoom(view.current.zoom*Math.exp(-delta*(event.ctrlKey ? .01 : .003)),index,{x:event.clientX,y:event.clientY});
      };
      pane.addEventListener('wheel',wheel,{passive:false});
      return()=>pane.removeEventListener('wheel',wheel);
    });
    return()=>{observer.disconnect();listeners.forEach(remove=>remove());cancelAnimationFrame(scheduled.current);};
  },[]);
  const loaded=()=>{
    setAvailable(pictures.current.some(image=>image?.complete && image.naturalWidth));
    schedule();
  };
  return <div className="frame-inspector">
    <div className="comparison-toolbar">
      <Text as="p" color="secondary" type="supporting" id="comparison-help">Zoom in, then drag either image to move both.</Text>
      <HStack gap={2} className="comparison-zoom" role="group" aria-label="Linked image zoom">
        <Button label="Zoom out" variant="ghost" onClick={()=>changeZoom(view.current.zoom/2)} isDisabled={!available || zoom<=1}/>
        <Text className="zoom-value" aria-label="Comparison magnification">{Number(zoom.toFixed(2))}×</Text>
        <Button label="Zoom in" variant="ghost" onClick={()=>changeZoom(view.current.zoom*2)} isDisabled={!available || zoom>=8}/>
        <Button label="Fit" variant="secondary" onClick={()=>changeZoom(1)} isDisabled={!available || zoom===1}/>
      </HStack>
    </div>
    <span className="sr-only" id="comparison-keys">Arrow keys move both images. Plus and minus zoom. Zero fits the frame. Double-click a detail to zoom in.</span>
    <div className="frame-pair">
      {frames.map(({label,url,dimensions,placeholder},index)=><figure key={label}>
        <figcaption><Text weight="medium">{label}</Text>{url && dimensions && <Text type="supporting" color="secondary">{dimensions.width} × {dimensions.height}</Text>}</figcaption>
        <div className="frame-image" ref={element=>{panes.current[index]=element;}} tabIndex={url?0:undefined} role="group" aria-label={`${label} image viewport`} aria-describedby="comparison-help comparison-keys"
          onKeyDown={event=>keyDown(event,index)}
          onDoubleClick={event=>{if(geometry(index))changeZoom(view.current.zoom===1?2:1,index,{x:event.clientX,y:event.clientY});}}
          onPointerDown={event=>{
            if(event.button!==0 || drag.current || view.current.zoom<=1 || !geometry(index))return;
            event.currentTarget.focus({preventScroll:true});event.currentTarget.setPointerCapture(event.pointerId);
            drag.current={id:event.pointerId,index,x:event.clientX,y:event.clientY};event.currentTarget.dataset.dragging='true';
          }}
          onPointerMove={event=>{
            const previous=drag.current;if(previous?.id!==event.pointerId)return;
            const g=geometry(previous.index);if(!g)return;
            view.current.x-=(event.clientX-previous.x)/(g.pictureWidth*view.current.zoom);
            view.current.y-=(event.clientY-previous.y)/(g.pictureHeight*view.current.zoom);
            previous.x=event.clientX;previous.y=event.clientY;schedule();
          }} onPointerUp={release} onPointerCancel={release} onLostPointerCapture={release}>
          {url?<img key={url} ref={element=>{pictures.current[index]=element;}} src={url} draggable={false} alt={`${label} ${description}`}
            onLoad={()=>{loaded();onLoad(label,url);}}
            onError={()=>{loaded();onError(label);}}/>:<Text as="p" color="secondary" type="supporting">{placeholder}</Text>}
        </div>
      </figure>)}
    </div>
  </div>;
}

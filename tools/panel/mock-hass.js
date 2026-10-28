/* Standalone local preview adapter. No network requests. */
(() => {
  const presets = [
    {id:'preview-sunset',alias:'Sunset',groups:['Home Assistant'],colorMode:'rgb',pattern:['FF9A3C','FF2200'],effects:[{effectType:'fade',value:128}],builtin:false},
    {id:'preview-sparkle',alias:'Sparkle',groups:['Home Assistant'],colorMode:'rgb',pattern:['FF9A3C','55AA00'],effects:[{effectType:'twinkle',value:100}],builtin:false}
  ];
  const zone={entry_id:'preview',bridge_serial:'preview-bridge',zone_serial:'preview-zone',entity_id:'light.preview_zone',name:'Preview zone',active:false,sequence:null,playlist:{running:false,presets:[],interval:60,shuffle:false}};
  const calls=[];
  const hass={states:{},themes:{darkMode:false},language:'en',
    async callWS(msg) {
      if(msg.type==='everlights_v3/zones') return structuredClone([zone]);
      if(msg.type==='everlights_v3/presets') return structuredClone(presets);
      throw new Error('Unexpected command '+msg.type);
    },
    async callService(domain,service,data,target) {
      calls.push({domain,service,data,target});console.log(domain,service,data,target);
      if(domain!=='everlights_v3') throw new Error('Unexpected domain');
      if(service==='save_preset') {
        const body={id:'preview-'+Date.now(),alias:data.name,pattern:data.colors,effects:data.effects.map(e=>({effectType:e.type,value:e.value})),groups:['Home Assistant'],colorMode:'rgb',builtin:false};
        const index=presets.findIndex(p=>p.alias===data.name);
        if(index>=0) presets[index]={...body,id:presets[index].id}; else presets.push(body);
      }
      if(service==='delete_preset') {const i=presets.findIndex(p=>p.id===data.preset||p.alias===data.preset);if(i>=0)presets.splice(i,1);}
      if(service==='start_playlist') zone.playlist={running:true,...data};
      if(service==='stop_playlist') zone.playlist.running=false;
      if(service==='set_pattern'||service==='play_preset')zone.playlist.running=false;
    }
  };
  window.mockHass=hass;window.MOCK_HASS=hass;window.mockCalls=calls;
})();
window.createMockHass = ({onLog}={}) => {
  let panel, fail=false;
  const hass=window.mockHass;
  const original=hass.callService.bind(hass);
  hass.callService=async (...args)=>{if(fail){fail=false;throw new Error('Preview simulated failure');}const r=await original(...args);onLog?.({kind:'callService',payload:args,result:r,time:new Date()});return r;};
  return {attach(p){panel=p;p.hass=hass;},setDarkMode(dark){hass.themes={darkMode:dark};if(panel)panel.hass={...hass};},failNext(){fail=true;},hass};
};

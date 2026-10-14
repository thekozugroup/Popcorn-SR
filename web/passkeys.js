// Native WebAuthn; binary fields cross the API as base64url.
function decode(value) { return Uint8Array.from(atob(value.replace(/-/g,'+').replace(/_/g,'/')),c=>c.charCodeAt(0)); }
function encode(value) { return btoa(String.fromCharCode(...new Uint8Array(value))).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,''); }
export function passkeysSupported() { return window.isSecureContext && !!window.PublicKeyCredential && !!navigator.credentials; }
export async function usePasskey(api, register=false) {
  if(!passkeysSupported())throw Error('Open the HTTPS address in a browser that supports passkeys.');
  const mode=register?'register':'login';
  const {request_id,options}=await api(`/api/auth/passkeys/${mode}/options`,{method:'POST'});
  const publicKey={...options,challenge:decode(options.challenge)};
  if(register){publicKey.user={...options.user,id:decode(options.user.id)};publicKey.excludeCredentials=(options.excludeCredentials||[]).map(c=>({...c,id:decode(c.id)}));}
  else if(options.allowCredentials)publicKey.allowCredentials=options.allowCredentials.map(c=>({...c,id:decode(c.id)}));
  let credential;
  try{credential=register?await navigator.credentials.create({publicKey}):await navigator.credentials.get({publicKey});}
  catch(e){if(e.name==='NotAllowedError' || e.name==='AbortError')throw Error('Passkey setup was cancelled. Try again or use your password.');throw Error('This device could not use the passkey. Try another device or use your password.');}
  if(!credential)throw Error('No passkey was selected. Try again.');
  const response={clientDataJSON:encode(credential.response.clientDataJSON)};
  if(register){response.attestationObject=encode(credential.response.attestationObject);response.transports=credential.response.getTransports?.()||[];}
  else{response.authenticatorData=encode(credential.response.authenticatorData);response.signature=encode(credential.response.signature);response.userHandle=credential.response.userHandle?encode(credential.response.userHandle):null;}
  return api(`/api/auth/passkeys/${mode}/verify`,{method:'POST',body:JSON.stringify({request_id,credential:{id:credential.id,rawId:encode(credential.rawId),type:credential.type,response,clientExtensionResults:credential.getClientExtensionResults(),authenticatorAttachment:credential.authenticatorAttachment}})});
}

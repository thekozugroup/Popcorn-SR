// Astryx 0.6.8 installs one static CSS sheet for selector placement at runtime.
// Authorize that exact sheet by hash; keep arbitrary inline styles/scripts blocked.
import {createHash} from 'node:crypto';
import {writeFileSync, readFileSync} from 'node:fs';
import {pathToFileURL} from 'node:url';
import {resolve} from 'node:path';
const root = resolve('node_modules/@astryxdesign/core');
const {slideRulesCss} = await import(pathToFileURL(`${root}/dist/Layer/layerSlideRules.js`));
const version = JSON.parse(readFileSync(`${root}/package.json`, 'utf8')).version;
const hash = `sha256-${createHash('sha256').update(slideRulesCss()).digest('base64')}`;
writeFileSync('popcorn_sr/static/ui-policy.json', JSON.stringify({astryx_version:version, style_hashes:[hash]})+'\n');
writeFileSync('popcorn_sr/static/.gitkeep', '');

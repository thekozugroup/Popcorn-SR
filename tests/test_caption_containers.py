import hashlib
import json
import subprocess

import pytest

from popcorn_sr.dlss import compatible_recipe
from popcorn_sr.engines import caption_copy_check
from popcorn_sr.media import ffmpeg_command, inspect_source, output_suffix, preserved_command, validate_output
from popcorn_sr.models import Recipe
from popcorn_sr.preview_cleanup import remove_preview
from tests.conftest import pair_worker


def captions_fixture(folder, kind):
    captions = folder / ('captions.scc' if kind == 'eia_608' else 'captions.srt')
    captions.write_text('Scenarist_SCC V1.0\n\n00:00:00:00\t9420 9420 c1c2 942f 942f\n\n00:00:01:00\t942c 942c\n\n'
                        if kind == 'eia_608' else '1\n00:00:00,000 --> 00:00:01,000\nOriginal caption\n')
    source = folder / ('source.mov' if kind == 'eia_608' else 'source.mp4')
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=128x96:rate=24',
                    '-f', 'lavfi', '-i', 'sine=sample_rate=48000', '-i', str(captions),
                    '-map', '0:v', '-map', '1:a', '-map', '2:s', '-t', '3', '-c:v', 'libx264',
                    '-bf', '0', '-c:a', 'aac', '-c:s', 'copy' if kind == 'eia_608' else 'mov_text', str(source)], check=True)
    return source


def caption_packets(path):
    data = subprocess.check_output(['ffprobe', '-v', 'error', '-select_streams', 's', '-show_packets',
                                    '-show_data_hash', 'sha256', '-of', 'json', str(path)])
    return [(p['pts_time'], p['data_hash']) for p in json.loads(data)['packets']]


@pytest.mark.parametrize('kind', ['eia_608', 'mov_text'])
@pytest.mark.parametrize('preview', [0, 5])
def test_real_caption_copy_and_generated_preview_deletion(tmp_path, kind, preview):
    source = captions_fixture(tmp_path, kind)
    original = inspect_source(source)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    recipe = Recipe(engine='resize', codec='h264', scale=1, preview_seconds=preview).model_dump()
    suffix = output_suffix(original, recipe)
    rendered = tmp_path / ('rendered' + suffix)
    subprocess.run(ffmpeg_command(source, rendered, recipe, original), check=True)
    validate_output(rendered, original, recipe)
    # Exercise the enhancement save step with a real zero-based video-only encode.
    video = tmp_path / 'video.mkv'
    subprocess.run(['ffmpeg', '-v', 'error', '-i', str(source), '-map', '0:v', '-vf', 'setpts=PTS-STARTPTS',
                    '-c:v', 'libx264', '-bf', '0', '-an', str(video)], check=True)
    output = tmp_path / ('enhanced' + suffix)
    subprocess.run(preserved_command(video, source, output, recipe, original), check=True)
    result = validate_output(output, original, recipe)
    assert caption_packets(output) == caption_packets(source)
    assert hashlib.sha256(source.read_bytes()).hexdigest() == digest
    assert result['subtitle_codecs'] == [kind]
    if preview:
        folder = tmp_path / 'copies'
        folder.mkdir()
        identity = 'owned-test'
        name = f'{source.stem}.preview.{identity}{suffix}'
        output.rename(folder / name)
        remove_preview(tmp_path, {'id': identity, 'path': source.name, 'source': original, 'recipe': recipe | {'output_directory': 'copies'},
                                  'status': 'completed', 'result': {'path': 'copies/' + name}})
        assert not (folder / name).exists() and source.exists() and rendered.exists()


def test_caption_capability_is_gated_and_unsupported_combinations_fail_early(tmp_path):
    assert caption_copy_check(tmp_path)
    recipe = Recipe().model_dump()
    source = {'subtitle_codecs': ['eia_608'], 'attachment_streams': 0}
    caps = {'engines': ['resize'], 'encoders': ['h264_cpu'], 'caption_copy': True}
    assert compatible_recipe(recipe, caps, source)
    assert not compatible_recipe(recipe, caps | {'caption_copy': False}, source)
    with pytest.raises(ValueError, match='H.264 or H.265'):
        output_suffix(source, recipe | {'codec': 'av1'})
    assert output_suffix(source, recipe | {'codec': 'av1', 'preview_frame_time': 0}) == '.mkv'
    with pytest.raises(ValueError, match='mixed captions'):
        output_suffix(source | {'attachment_streams': 1}, recipe)
    with pytest.raises(ValueError, match='mixed captions'):
        output_suffix(source | {'subtitle_codecs': ['eia_608', 'ass']}, recipe)


def test_manager_publishes_and_deletes_caption_preserving_preview(setup, auth):
    client, store, cfg, _ = setup
    source = captions_fixture(cfg.library, 'eia_608')
    credentials, _ = pair_worker(client)
    body = {'path': source.name, 'recipe': {'scale': 1, 'preview_seconds': 5}}
    assert client.post('/api/jobs', json=body).status_code == 400
    credentials, _ = pair_worker(client, {'engines': ['resize'], 'encoders': ['h264_cpu'], 'caption_copy': True})
    body['worker_id'] = credentials['worker_id']
    response = client.post('/api/jobs', json=body)
    assert response.status_code == 200, response.text
    identity = response.json()['id']
    headers = {'Authorization': 'Bearer ' + credentials['token']}
    claim = client.post('/api/worker/claim', headers=headers).json()['job']
    output = cfg.library / 'return.mov'
    subprocess.run(ffmpeg_command(source, output, claim['recipe'], claim['source']), check=True)
    data = output.read_bytes()
    response = client.put(f'/api/worker/jobs/{identity}/result', content=data,
                          headers=headers | {'X-Job-Lease': claim['lease'], 'X-Output-SHA256': hashlib.sha256(data).hexdigest()})
    assert response.status_code == 200, response.text
    saved = cfg.output / response.json()['result']['path']
    assert saved.suffix == '.mov' and saved.exists()
    assert caption_packets(saved) == caption_packets(source)
    assert client.get(f'/api/jobs/{identity}/download').headers['content-type'] == 'video/quicktime'
    assert client.delete(f'/api/jobs/{identity}/preview').status_code == 200
    assert not saved.exists() and source.exists() and store.job(identity) is None

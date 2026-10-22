"""Check exported tutorial media, speech track, captions, chapter bounds and manifests."""
from pathlib import Path
import argparse,json,re,subprocess
ROOT=Path(__file__).resolve().parents[1]
def timestamp(value):
    h,m,s=value.split(':');return int(h)*3600+int(m)*60+float(s)
def check(ffprobe):
    media=json.loads(subprocess.check_output(['node','--input-type=module','-e',"import {HELP_MEDIA} from './frontend/help-media.js'; console.log(JSON.stringify(HELP_MEDIA))"],cwd=ROOT))
    counts={'videos':0,'chapters':0,'captions':0};issues=[]
    for topic,base in media.items():
        for kind,item in [('overview',base),*([('filling',base['filling'])] if base.get('filling') else [])]:
            try:
                video=ROOT/'frontend'/item['src'].removeprefix('/assets/')
                data=json.loads(subprocess.check_output([ffprobe,'-v','error','-show_streams','-show_format','-of','json',str(video)]))
                duration=float(data['format']['duration']);streams=data['streams']
                assert any(s['codec_type']=='video' and s['codec_name']=='h264' and s['width']>=1280 for s in streams),'Video codec/size mismatch'
                assert any(s['codec_type']=='audio' and s['codec_name']=='aac' for s in streams),'Speech track missing'
                assert abs(duration-item['duration'])<1.5,'Duration mismatch'
                assert all(0<=c['time']<duration for c in item['chapters']),'Chapter out of range'
                text=(ROOT/'frontend'/item['captions'].removeprefix('/assets/')).read_text(encoding='utf-8')
                assert text.startswith('WEBVTT'),'Caption header missing'
                cues=re.findall(r'(\d\d:\d\d:\d\d\.\d{3}) --> (\d\d:\d\d:\d\d\.\d{3})',text)
                assert cues,'No captions'
                previous=0
                for start,end in cues:
                    a,b=timestamp(start),timestamp(end);assert previous-.03<=a<b<=duration+1,'Caption timing mismatch';previous=b
                assert 'private-login' not in text and 'FixtureOnly_' not in text,'Private data in captions'
                counts['videos']+=1;counts['chapters']+=len(item['chapters']);counts['captions']+=len(cues)
            except Exception as error:issues.append({'topic':topic,'kind':kind,'error':str(error)})
    print(json.dumps({'checked':counts,'issues':issues},ensure_ascii=False,indent=2))
    if issues:raise SystemExit(1)
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--ffprobe',required=True);check(parser.parse_args().ffprobe)

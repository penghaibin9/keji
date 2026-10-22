"""Scan the generated handbook and captions for wording problems teachers have reported.

Counts “。；” joins, doubled full stops, repeated sentences, captions that start with a comma
or run too long, split codes, and test-account names. Exits non-zero when any count is not 0.
用法：python scripts/check_help_text.py
"""
from pathlib import Path
import json,re,sys
ROOT=Path(__file__).resolve().parents[1]
VERSION=re.search(r"HELP_VERSION='(\d{8})'",(ROOT/'frontend/help-content.js').read_text(encoding='utf-8'))[1]
ACCOUNTS=re.compile(r'J00\d|schooladmin|collegehead|depthead|otherdept|\breviewer\b|\bteacher\b|private-login|FixtureOnly_|HELP-PROJECT|HELP-FLOW|隔离测试|测试教师|测试学院|测试教研室',re.I)
SENTENCE=re.compile(r'[^。！？\n|]+[。！？]')

def cue_texts(text):
    return [block.split('\n',1)[1].strip() for block in text.strip().split('\n\n')[1:] if '\n' in block]

def scan():
    manual=ROOT/f'docs/用户操作手册_系统内版_{VERSION}.md'
    captions=sorted((ROOT/'frontend/assets/help'/VERSION).glob('*.vtt'))
    counts={'“。；”拼接':0,'“。。”':0,'同一行重复的句子':0,'测试账号或演示编号':0,'以“，”开头的字幕':0,'超过 22 字的字幕':0,'被拆开的编号':0,'字幕里重复的句子':0}
    found={k:[] for k in counts}
    def hit(kind,where):counts[kind]+=1;found[kind].append(where) if len(found[kind])<8 else None
    text=manual.read_text(encoding='utf-8')
    for n,line in enumerate(text.splitlines(),1):
        where=f'{manual.name}:{n}'
        for _ in range(line.count('。；')):hit('“。；”拼接',where)
        for _ in re.findall('。{2,}',line):hit('“。。”',where)
        sentences=[s.strip() for s in SENTENCE.findall(line) if len(s.strip())>5]
        if len(sentences)!=len(set(sentences)):hit('同一行重复的句子',where)
        for _ in ACCOUNTS.findall(line):hit('测试账号或演示编号',where)
    for file in captions:
        cues=cue_texts(file.read_text(encoding='utf-8'))
        for i,cue in enumerate(cues):
            where=f'{file.name}#{i+1}'
            if cue.startswith(('，','、','；','。')):hit('以“，”开头的字幕',where)
            if len(cue.rstrip('。！？'))>22:hit('超过 22 字的字幕',where)  # 句末标点不计字数
            for _ in re.findall('。{2,}',cue):hit('“。。”',where)
            for _ in range(cue.count('。；')):hit('“。；”拼接',where)
            for _ in ACCOUNTS.findall(cue):hit('测试账号或演示编号',where)
            if i+1<len(cues) and re.search(r'[A-Za-z0-9-]$',cue) and re.match(r'[A-Za-z0-9-]',cues[i+1]):hit('被拆开的编号',where)
        # 不同字段各自的限制说明（如“不能填负数，最多保留两位小数”）本来就会相同，不算配音重复。
        spoken=[s for s in SENTENCE.findall(''.join(cues)) if len(s)>8 and not re.match(r'(不能|最多|只能|可以填|支持|可选)',s)]
        repeated=len(spoken)-len(set(spoken))
        for _ in range(repeated):hit('字幕里重复的句子',file.name)
    return {'manual':manual.name,'captions':len(captions),'counts':counts,'examples':{k:v for k,v in found.items() if v}}

if __name__=='__main__':
    result=scan();print(json.dumps(result,ensure_ascii=False,indent=2))
    if any(result['counts'].values()):sys.exit(1)

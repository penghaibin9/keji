"""Validate the installed tutorial file set without requiring Node or video tooling."""
from pathlib import Path
import json,re

def validate_help_assets(root,selected=None):
    root=Path(root);content=root/'frontend/help-content.js'
    if not content.exists():return []  # Older packages without integrated help retain their original checks.
    issues=[]
    try:
        source=content.read_text(encoding='utf-8')
        version=re.search(r"HELP_VERSION='(\d{8})'",source)[1]
        topics=set(re.findall(r"^\s*\['([a-z_]+)','",source,re.M))
        def module(name,export):
            return json.loads((root/'frontend'/name).read_text(encoding='utf-8').split('export const '+export+'=',1)[1].strip().removesuffix(';'))
        media=module('help-media.js','HELP_MEDIA');forms=module('help-forms.js','HELP_FORMS')
        required={'frontend/help-system.js','frontend/help-system.css','frontend/help-content.js','frontend/help-media.js','frontend/help-forms.js',f'frontend/assets/help/{version}/manual.html',f'frontend/assets/help/{version}/manual.pdf'}
        for topic in topics:
            for form in forms.get(topic,[]):
                for field in form.get('fields',[]):
                    if not field.get('documented') or not field.get('explanation','').strip():issues.append(topic+'：字段缺少具体说明：'+field.get('label','未命名字段'))
            item=media.get(topic)
            if not item:issues.append(topic+'：缺少操作视频');continue
            if forms.get(topic) and not item.get('filling'):issues.append(topic+'：缺少逐项填写视频')
            elif forms.get(topic):
                for form in forms[topic]:
                    if form['title'] not in item['filling'].get('covered_forms',[]):issues.append(topic+'：新表单缺少填写视频覆盖：'+form['title'])
            for clip in [item,*([item['filling']] if item.get('filling') else [])]:
                if clip.get('version')!=version:issues.append(topic+'：媒体与手册版本不一致')
                for key in ('src','poster','captions'):
                    value=clip.get(key,'')
                    if not value.startswith(f'/assets/assets/help/{version}/') or '..' in value or '\\' in value:
                        issues.append(topic+'：非法媒体路径');continue
                    required.add('frontend/'+value.removeprefix('/assets/'))
                chapters=clip.get('chapters',[])
                if not chapters or any(not 0<=c.get('time',-1)<clip.get('duration',0) for c in chapters):issues.append(topic+'：章节时间缺失或超出视频范围')
        for name in sorted(required):
            p=root/name
            if not p.is_file() or not p.stat().st_size:issues.append(name+'：资源缺失或为空')
            elif selected is not None and name not in selected:issues.append(name+'：资源未纳入交付包')
    except (ValueError,KeyError,IndexError,TypeError,OSError) as error:issues.append('帮助清单无法解析：'+str(error))
    return issues

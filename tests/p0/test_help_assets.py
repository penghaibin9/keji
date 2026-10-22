import json
from help_assets import validate_help_assets

def put(root,name,text='fixture'):
    file=root/name;file.parent.mkdir(parents=True,exist_ok=True);file.write_text(text,encoding='utf-8')

def test_partial_help_package_is_blocked_even_when_main_video_exists(tmp_path):
    put(tmp_path,'frontend/help-content.js',"export const HELP_VERSION='20261022';\n ['course','课程','说明'],\n")
    clip={'version':'20261022','duration':12,'chapters':[{'time':0,'title':'开始'}]}
    for key,ext in [('src','mp4'),('poster','jpg'),('captions','vtt')]:
        clip[key]='/assets/assets/help/20261022/course.'+ext;put(tmp_path,'frontend/assets/help/20261022/course.'+ext)
    put(tmp_path,'frontend/help-media.js','export const HELP_MEDIA='+json.dumps({'course':clip})+';')
    put(tmp_path,'frontend/help-forms.js','export const HELP_FORMS={"course":[{"title":"申请"}]};')
    issues=validate_help_assets(tmp_path)
    assert any('逐项填写视频' in i for i in issues)
    assert any('manual.html' in i for i in issues)

def test_legacy_package_is_unaffected(tmp_path):
    assert validate_help_assets(tmp_path)==[]

def test_new_form_requires_its_own_video_coverage(tmp_path):
    put(tmp_path,'frontend/help-content.js',"export const HELP_VERSION='20261022';\n ['course','课程','说明'],\n")
    clip={'version':'20261022','duration':12,'chapters':[{'time':0,'title':'开始'}],'src':'/assets/assets/help/20261022/course.mp4','poster':'/assets/assets/help/20261022/course.jpg','captions':'/assets/assets/help/20261022/course.vtt','covered_forms':['旧申请']}
    put(tmp_path,'frontend/help-media.js','export const HELP_MEDIA='+json.dumps({'course':{**clip,'filling':clip}})+';')
    put(tmp_path,'frontend/help-forms.js','export const HELP_FORMS={"course":[{"title":"新申请","fields":[]}]};')
    assert any('新表单缺少填写视频覆盖：新申请' in issue for issue in validate_help_assets(tmp_path))

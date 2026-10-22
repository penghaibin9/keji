"""Render the shared handbook content with bounded memory; no browser or external service."""
from pathlib import Path
import json,subprocess,re
from xml.sax.saxutils import escape
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,PageBreak,LongTable,Table,TableStyle,Image,KeepTogether
from pypdf import PdfReader
ROOT=Path(__file__).resolve().parents[1]
DATA=json.loads(subprocess.check_output(['node','--input-type=module','-e',"import {HELP_VERSION,HELP_TOPICS,HELP_FAQS,ROLE_NAMES} from './frontend/help-content.js';import {HELP_FORMS} from './frontend/help-forms.js';import {HELP_MEDIA} from './frontend/help-media.js';import {fieldSentences,requirementText} from './frontend/help-system.js';for(const forms of Object.values(HELP_FORMS))for(const f of forms)for(const x of f.fields){x.sentences=fieldSentences(x);x.requirement_text=requirementText(x)}console.log(JSON.stringify({version:HELP_VERSION,topics:HELP_TOPICS,faqs:HELP_FAQS,roles:ROLE_NAMES,forms:HELP_FORMS,media:HELP_MEDIA}))"],cwd=ROOT))
VERSION=DATA['version'];TARGET=ROOT/'frontend/assets/help'/VERSION
pdfmetrics.registerFont(TTFont('HelpCN','C:/Windows/Fonts/msyh.ttc',subfontIndex=0))
pdfmetrics.registerFont(TTFont('HelpCNBold','C:/Windows/Fonts/msyhbd.ttc',subfontIndex=0))
pdfmetrics.registerFontFamily('HelpCN',normal='HelpCN',bold='HelpCNBold',italic='HelpCN',boldItalic='HelpCNBold')
STYLE={
 'title':ParagraphStyle('title',fontName='HelpCNBold',fontSize=24,leading=34,textColor=colors.HexColor('#184e76'),spaceAfter=18),
 'chapter':ParagraphStyle('chapter',fontName='HelpCNBold',fontSize=17,leading=25,textColor=colors.HexColor('#184e76'),spaceAfter=12,keepWithNext=True),
 'sub':ParagraphStyle('sub',fontName='HelpCNBold',fontSize=12,leading=19,spaceBefore=12,spaceAfter=8,keepWithNext=True),
 'body':ParagraphStyle('body',fontName='HelpCN',fontSize=10.5,leading=18,wordWrap='CJK',spaceAfter=8),
 'cell':ParagraphStyle('cell',fontName='HelpCN',fontSize=9.5,leading=15,wordWrap='CJK'),
 'small':ParagraphStyle('small',fontName='HelpCN',fontSize=8,leading=12,textColor=colors.HexColor('#566b7e'),spaceAfter=8),
}
def paragraph(text,kind='body'):
    return Paragraph(escape(str(text)).replace('\n','<br/>'),STYLE[kind])
class NumberedCanvas(canvas.Canvas):
    def __init__(self,*a,**kw):super().__init__(*a,**kw);self.states=[]
    def showPage(self):self.states.append(dict(self.__dict__));self._startPage()
    def save(self):
        total=len(self.states)
        for state in self.states:
            self.__dict__.update(state);self.setFont('HelpCN',8);self.setFillColor(colors.HexColor('#62758a'))
            self.drawString(36,22,'系统操作手册 · '+VERSION+'版 · 虚构教学资料')
            self.drawRightString(A4[0]-36,22,f'第 {self._pageNumber} 页 / 共 {total} 页')
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)

def run():
    width=A4[0]-72;story=[paragraph('系统操作手册\n与逐页填写指南','title'),paragraph('适用版本：'+VERSION),paragraph('在业务页面点击“使用帮助”，在表单中点击“填写说明”或字段旁“怎么填”。在帮助中心按身份、业务或问题查找，也可观看配音视频并直接跳到某个填写项。'),paragraph('本手册与系统内帮助使用同一份内容。画面与示例均为虚构教学资料，实际人员、数据、审批职责和制度口径以学校确认及当前业务页面为准。'),paragraph('阅读目录','sub')]
    titles=[t['title'] for t in DATA['topics']];toc=[]
    for i in range(0,len(titles),2):toc.append([paragraph(str(i+1)+'、'+titles[i],'cell'),paragraph(str(i+2)+'、'+titles[i+1],'cell') if i+1<len(titles) else ''])
    table=Table(toc,colWidths=[width/2]*2);table.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('BOTTOMPADDING',(0,0),(-1,-1),6)]));story.append(table)
    for index,topic in enumerate(DATA['topics'],1):
        story.extend([PageBreak(),paragraph(str(index)+'、'+topic['title'],'chapter'),paragraph(topic['purpose'])])
        story.extend(paragraph(str(i)+'、'+step) for i,step in enumerate(topic['steps'],1))
        story.append(paragraph('完成标志：'+topic['done']))
        media=DATA['media'].get(topic['id']);assert media,'Missing video/illustration: '+topic['id']
        poster=ROOT/'frontend'/media['poster'].removeprefix('/assets/');assert poster.is_file()
        pic=Image(str(poster));ratio=min(width/pic.imageWidth,310/pic.imageHeight);pic.drawWidth=pic.imageWidth*ratio;pic.drawHeight=pic.imageHeight*ratio
        story.append(KeepTogether([Spacer(1,6),pic,paragraph('界面位置示意；具体填写要求见下表。画面均为虚构资料。','small')]))
        for form in DATA['forms'].get(topic['id'],[]):
            role=DATA['roles'].get(form.get('role'),'对应办理人员')
            story.extend([paragraph(form['title']+'（'+role+'）：每项怎么填','sub'),paragraph('下列必填性为采集时的表单条件。实际填写时，条件会随选项变化，以当前表单提示为准。','small')])
            rows=[[paragraph('填写项','cell'),paragraph('含义、示例和限制','cell')]]
            for field in form['fields']:
                rows.append([paragraph(field['label']+('\n'+field['requirement_text'] if field['requirement_text'] else ''),'cell'),paragraph('\n'.join(field['sentences']),'cell')])
            table=LongTable(rows,colWidths=[width*.27,width*.73],repeatRows=1,hAlign='LEFT',rowSplitRange=(2,-2))
            table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#eaf2fa')),('GRID',(0,0),(-1,-1),.4,colors.HexColor('#d1dce6')),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]));story.append(table)
    story.extend([PageBreak(),paragraph('常见问题','chapter')])
    for question,answer in DATA['faqs']:story.extend([paragraph(question,'sub'),paragraph(answer)])
    output=TARGET/'manual.pdf';SimpleDocTemplate(str(output),pagesize=A4,rightMargin=36,leftMargin=36,topMargin=36,bottomMargin=42,title='系统操作手册与逐页填写指南',author='系统操作教学资料').build(story,canvasmaker=NumberedCanvas)
    reader=PdfReader(output);text='\n'.join(p.extract_text() for p in reader.pages)
    for topic in DATA['topics']:assert topic['title'] in text,'Missing chapter: '+topic['title']
    for key in ['提交项目结项','本人积分申报','登记外聘培训师','常见问题']:assert key in text
    normalized=''.join(text.split())
    for form in [f for forms in DATA['forms'].values() for f in forms]:
        for field in form['fields']:assert ''.join(field['explanation'].split()) in normalized,'Missing field explanation: '+field['label']
    assert all(p.extract_text().strip() for p in reader.pages)
    print('可打印手册已生成，共'+str(len(reader.pages))+'页。')
if __name__=='__main__':run()

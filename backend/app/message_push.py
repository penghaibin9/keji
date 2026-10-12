"""待办推送到学校移动门户（湖科职消息中心 send/send 接口）。

默认关闭：只有配置了 ND_MESSAGE_PUSH_YYID（学校给的应用 ID）才会发。鉴权靠学校把服务器出口 IP 加白名单，
本系统不保存任何密钥。推送在业务事务提交之后另起线程发送，失败只记日志，不影响老师办理业务；
老师点开消息进入“个人培训”，待办在页面最上面。
"""
import json
import logging
import threading
from contextvars import ContextVar
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

log = logging.getLogger('nondegree.message_push')
_pending: ContextVar[list | None] = ContextVar('message_push_pending', default=None)
JSRID_BATCH = 100
TITLE_MAX, DESC_MAX = 100, 200  # 文档正文写 100/200 字，返回码说明写 20 字，需与学校实测确认


def begin():
    """command() 开始时调用：本次业务写入期间要推送的消息先暂存，提交成功后再发。"""
    return _pending.set([])


def queue(db, user_ids, title, desc):
    """业务代码里登记一条待推送消息；只推给有工号的账号。未在 command() 内调用时忽略。"""
    box = _pending.get()
    if box is None: return
    from .models import User
    staff = sorted({u.staff_no for u in (db.get(User, i) for i in user_ids if i) if u and u.staff_no})
    # 全校重算考核时接收人可能上百，按批拆开，避免一条消息的接收人串过长被学校接口拒收。
    for i in range(0, len(staff), JSRID_BATCH):
        box.append({'jsrid': ','.join(staff[i:i + JSRID_BATCH]), 'title': title[:TITLE_MAX], 'desc': desc[:DESC_MAX]})


def finish(token, settings, committed):
    box = _pending.get() or []
    _pending.reset(token)
    if not committed or not box or not settings.message_push_yyid: return []
    endpoint = settings.message_push_endpoint
    if urlsplit(endpoint).scheme != 'https': log.warning('消息推送地址必须是 https，已跳过'); return []
    url = settings.public_origin + '/#mine'
    bodies = [{'yyid': settings.message_push_yyid, 'url': url if url.startswith('https://') else '', **x} for x in box]
    threading.Thread(target=_send_all, args=(endpoint, bodies), daemon=True).start()
    return bodies


def _send_all(endpoint, bodies):
    for body in bodies:
        try:
            req = Request(endpoint, data=json.dumps(body, ensure_ascii=False).encode(), headers={'Content-Type': 'application/json'}, method='POST')
            with urlopen(req, timeout=5) as resp:
                text = resp.read(2000).decode('utf-8', 'replace')
            log.info('消息推送已发送 %s 人：%s', body['jsrid'].count(',') + 1, text[:200])
        except Exception as err:  # 推送失败不影响业务，只留日志供排查
            log.warning('消息推送失败：%s', err)

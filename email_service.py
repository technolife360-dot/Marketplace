"""Transactional email delivery for account actions and order updates."""
from __future__ import annotations

from email.message import EmailMessage
from email.utils import parseaddr
from html import escape
from urllib.parse import quote, urlsplit
import os
import json
import smtplib
import ssl
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


def is_configured() -> bool:
    provider=os.environ.get('EMAIL_PROVIDER','disabled').strip().lower()
    sender=os.environ.get('EMAIL_FROM','').strip()
    address=parseaddr(sender)[1]
    if not address or '@' not in address: return False
    if os.environ.get('MARKETPLACE_MODE','development').lower()=='production':
        domain=address.rsplit('@',1)[1].lower()
        if domain=='resend.dev' or domain.endswith('.resend.dev'): return False
    if provider=='resend':
        return bool((os.environ.get('RESEND_API_KEY') or os.environ.get('EMAIL_API_KEY') or '').strip())
    return (provider=='smtp' and bool(os.environ.get('SMTP_HOST','').strip())
            and bool(os.environ.get('SMTP_USERNAME','').strip())
            and bool(os.environ.get('SMTP_PASSWORD',''))
            and os.environ.get('SMTP_PORT','').isdigit())


def _from_address() -> str:
    return os.environ.get('EMAIL_FROM','').strip()


def _deliver(message: EmailMessage, *, idempotency_key: str = '') -> None:
    if not is_configured(): raise RuntimeError('Transactional email is not configured')
    if os.environ.get('EMAIL_PROVIDER','disabled').strip().lower()=='resend':
        plain=message.get_body(preferencelist=('plain',))
        rich=message.get_body(preferencelist=('html',))
        payload={'from':str(message['From']),'to':[str(message['To'])],'subject':str(message['Subject']),
                 'text':plain.get_content() if plain else '', 'html':rich.get_content() if rich else ''}
        key=(os.environ.get('RESEND_API_KEY') or os.environ.get('EMAIL_API_KEY') or '').strip()
        req=Request('https://api.resend.com/emails',data=json.dumps(payload).encode(),headers={
            'Authorization':'Bearer '+key,'Content-Type':'application/json','User-Agent':'SentryLoot/1.0'},method='POST')
        if idempotency_key: req.add_header('Idempotency-Key',idempotency_key)
        try:
            with urlopen(req,timeout=12) as response:
                if not 200<=response.status<300: raise RuntimeError('Resend rejected the email request')
                response.read(4096)
        except HTTPError as exc: raise RuntimeError(f'Resend API returned HTTP {exc.code}') from None
        except URLError: raise RuntimeError('Resend API connection failed') from None
        return
    host=os.environ['SMTP_HOST'].strip(); port=int(os.environ.get('SMTP_PORT','587'))
    username=os.environ['SMTP_USERNAME'].strip(); password=os.environ['SMTP_PASSWORD']
    context=ssl.create_default_context()
    if port==465:
        with smtplib.SMTP_SSL(host,port,timeout=12,context=context) as client:
            client.login(username,password); client.send_message(message)
    else:
        with smtplib.SMTP(host,port,timeout=12) as client:
            client.ehlo(); client.starttls(context=context); client.ehlo()
            client.login(username,password); client.send_message(message)


def _brand_html(preheader: str, title: str, name: str, paragraphs: list[str], button: str, url: str, footer: str, details: list[tuple[str,str]] | None = None) -> str:
    rows=''.join(f'<tr><td style="padding:0 0 13px;font:15px/1.65 -apple-system,BlinkMacSystemFont,Segoe UI,Arial,sans-serif;color:#43564c">{escape(p)}</td></tr>' for p in paragraphs)
    facts=''
    if details:
        facts='<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:8px 0 22px;border:1px solid #e7eee8;border-radius:12px;background:#f7faf7">'+''.join(f'<tr><td style="padding:10px 14px;font:12px Arial,sans-serif;color:#64756b">{escape(k)}</td><td align="right" style="padding:10px 14px;font:13px Arial,sans-serif;font-weight:700;color:#17271d">{escape(v)}</td></tr>' for k,v in details)+'</table>'
    return (f'<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light"></head>'
        f'<body style="margin:0;padding:0;background:#f1f5f1"><div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent">{escape(preheader)}</div>'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f1"><tr><td align="center" style="padding:30px 14px">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;background:#fff;border:1px solid #e4ebe5;border-radius:18px;overflow:hidden">'
        f'<tr><td style="padding:23px 30px;background:#101a14"><table role="presentation" width="100%"><tr><td style="font:800 18px Arial,sans-serif;letter-spacing:1px;color:#fff">SENTRY<span style="color:#b9df91">LOOT</span></td><td align="right" style="font:11px Arial,sans-serif;color:#a9baae">GAMING MARKETPLACE</td></tr></table></td></tr>'
        f'<tr><td style="padding:34px 30px 14px"><div style="display:inline-block;padding:6px 10px;border-radius:20px;background:#eff7e8;color:#507237;font:700 10px Arial,sans-serif;letter-spacing:1px">SENTRYLOOT ACCOUNT</div>'
        f'<h1 style="margin:17px 0 10px;font:700 27px/1.2 -apple-system,BlinkMacSystemFont,Segoe UI,Arial,sans-serif;color:#17271d">{escape(title)}</h1>'
        f'<p style="margin:0 0 20px;font:14px Arial,sans-serif;color:#43564c">Salom, {escape(name)}!</p><table role="presentation" width="100%" cellpadding="0" cellspacing="0">{rows}</table>{facts}'
        f'<table role="presentation" cellpadding="0" cellspacing="0" style="margin:24px 0"><tr><td bgcolor="#b9df91" style="border-radius:10px"><a href="{escape(url,quote=True)}" style="display:inline-block;padding:14px 21px;border:1px solid #b9df91;border-radius:10px;color:#15231a;text-decoration:none;font:700 14px Arial,sans-serif">{escape(button)}</a></td></tr></table>'
        f'<p style="margin:0 0 20px;font:12px/1.6 Arial,sans-serif;color:#708077">{escape(footer)}</p><hr style="border:0;border-top:1px solid #edf1ed;margin:18px 0 14px">'
        f'<p style="margin:0;font:11px/1.6 Arial,sans-serif;color:#819087">SentryLoot · Xavfsiz o‘yin bozori<br>Agar tugma ishlamasa, ushbu manzilni brauzeringizga nusxalang:<br><span style="word-break:break-all;color:#507237">{escape(url)}</span></p></td></tr>'
        f'<tr><td style="padding:17px 30px;background:#f8faf8;font:10px/1.5 Arial,sans-serif;color:#8a978e">Bu avtomatik xizmat xabari. Javob berish shart emas.</td></tr></table>'
        f'<p style="margin:14px 0 0;font:10px Arial,sans-serif;color:#9aa69d">© 2026 SentryLoot</p></td></tr></table></body></html>')


def action_link(kind: str, token: str) -> str:
    routes = {'verify': 'verify', 'password_reset': 'password-reset-confirm','email_change':'email-change'}
    if kind not in routes:
        raise ValueError('Unsupported email action')
    base = os.environ.get('PUBLIC_BASE_URL', '').strip().rstrip('/')
    parsed = urlsplit(base)
    if parsed.scheme not in ('http', 'https') or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError('PUBLIC_BASE_URL must be an absolute HTTP(S) URL')
    if os.environ.get('MARKETPLACE_MODE', 'development').lower() == 'production' and parsed.scheme != 'https':
        raise ValueError('PUBLIC_BASE_URL must use HTTPS in production')
    return f'{base}/#{routes[kind]}/{quote(token, safe="")}'


def send_action_email(address: str, display_name: str, kind: str, token: str, language: str = 'uz') -> None:
    if language in ('en','ru'):return _localized_email(address,display_name,language,kind,token=token)
    if not is_configured():
        raise RuntimeError('Transactional email is not configured')

    copy = {
        'verify': ('Email manzilingizni tasdiqlang', 'Email manzilingizni tasdiqlash havolasi 24 soat amal qiladi.', 'Emailni tasdiqlash'),
        'email_change': ('Yangi emailni tasdiqlash','Emailni o‘zgartirish uchun havolani oching. Havola 30 daqiqa amal qiladi.','Emailni tasdiqlash'),
        'password_reset': ('Parolni tiklash', 'Parolni yangilash uchun havolani oching. Havola 30 daqiqada tugaydi.', 'Parolni tiklash'),
    }
    if kind not in copy:
        raise ValueError('Unsupported email action')
    subject, description, button = copy[kind]
    url = action_link(kind, token)
    name = display_name.strip() or 'foydalanuvchi'
    message = EmailMessage()
    message['Subject'] = f'SentryLoot — {subject}'
    message['From'] = _from_address()
    message['To'] = address
    message.set_content(
        f'Salom, {name}.\n\n{description}\n\n{url}\n\nAgar bu so‘rovni siz boshlamagan bo‘lsangiz, xatni e’tiborsiz qoldiring.'
    )
    footer='Agar bu so‘rovni siz boshlamagan bo‘lsangiz, ushbu xatni e’tiborsiz qoldiring.'
    message.add_alternative(_brand_html(description,subject,name,[description],button,url,footer),subtype='html')
    _deliver(message)


def send_order_update(address: str, display_name: str, reference: str, status: str, description: str, language: str = 'uz') -> None:
    if language in ('en','ru'):return _localized_email(address,display_name,language,'order',reference=reference,status=status)
    """Send a minimal order status email; never include credentials or delivery secrets."""
    if not is_configured():
        raise RuntimeError('Transactional email is not configured')
    base = os.environ.get('PUBLIC_BASE_URL', '').strip().rstrip('/')
    parsed = urlsplit(base)
    if parsed.scheme not in ('http', 'https') or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError('PUBLIC_BASE_URL must be an absolute HTTP(S) URL')
    if os.environ.get('MARKETPLACE_MODE', 'development').lower() == 'production' and parsed.scheme != 'https':
        raise ValueError('PUBLIC_BASE_URL must use HTTPS in production')
    name = display_name.strip() or 'foydalanuvchi'
    url = f'{base}/#orders'
    subject = f'SentryLoot — buyurtma {reference}: {status}'
    message = EmailMessage()
    message['Subject'] = subject
    message['From'] = _from_address()
    message['To'] = address
    message.set_content(f'Salom, {name}.\n\n{description}\nBuyurtma: {reference}\nHolat: {status}\n\nBuyurtmalarni ko‘rish: {url}\n\nXavfsizlik uchun emailda parol yoki yetkazish ma’lumotlari yuborilmaydi.')
    footer='Xavfsizlik uchun emailda parol yoki maxfiy yetkazish ma’lumotlari yuborilmaydi.'
    message.add_alternative(_brand_html(description,'Buyurtma yangilandi',name,[description],'Buyurtmalarni ko‘rish',url,footer,[('Buyurtma',reference),('Holat',status)]),subtype='html')
    _deliver(message)


def send_security_update(address: str, display_name: str, description: str, language: str = 'uz') -> None:
    if language in ('en','ru'):return _localized_email(address,display_name,language,'security')
    """Security event notification. Never include passwords, OTPs or setup keys."""
    if not is_configured(): raise RuntimeError('Transactional email is not configured')
    message=EmailMessage()
    message['Subject']='SentryLoot — hisob xavfsizligi'
    message['From']=_from_address()
    message['To']=address
    message.set_content(f'Salom, {display_name}.\n\n{description}.\nBu amalni siz bajarmagan bo‘lsangiz, gamestorehub.com orqali yordam xizmatiga murojaat qiling.')
    _deliver(message)


def send_verification_update(address: str, display_name: str, title: str, description: str, notification_id: str) -> None:
    """Send the exact persisted admin decision, with a stable provider retry key."""
    base=os.environ.get('PUBLIC_BASE_URL','').strip().rstrip('/')
    parsed=urlsplit(base)
    if parsed.scheme not in ('https','http') or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError('PUBLIC_BASE_URL must be an absolute URL')
    if os.environ.get('MARKETPLACE_MODE','development').lower()=='production' and parsed.scheme!='https':
        raise ValueError('HTTPS is required')
    url=base+'/#seller'
    message=EmailMessage(); message['Subject']='SentryLoot — '+title
    message['From']=_from_address(); message['To']=address
    message.set_content(f'Hello, {display_name}.\n\n{description}\n\nView verification: {url}')
    message.add_alternative(f'<!doctype html><html lang="en"><body style="margin:0;background:#000;color:#f1f1f1;font:15px/1.6 Roboto,Arial,sans-serif">'
        f'<main style="max-width:560px;margin:32px auto;padding:28px;background:#111;border:1px solid #333;border-radius:16px">'
        f'<div style="font-size:22px;font-weight:700">Sentry<span style="color:#ff9b42">Loot</span></div>'
        f'<h1 style="font-size:23px">{escape(title)}</h1><p>Hello, {escape(display_name)}.</p><p>{escape(description)}</p>'
        f'<a href="{escape(url,quote=True)}" style="display:inline-block;margin-top:12px;padding:12px 18px;background:#ff9b42;color:#000;border-radius:8px;text-decoration:none;font-weight:700">View verification</a>'
        f'<p style="color:#aaa;font-size:12px">This is an account verification update from SentryLoot.</p></main></body></html>',subtype='html')
    _deliver(message,idempotency_key='seller-review/'+notification_id)


def send_marketplace_alert(address: str, display_name: str, title: str, language: str = 'uz') -> None:
    if language in ('en','ru'):return _localized_email(address,display_name,language,'notification')
    """Opt-in discovery/chat alert. Never email private chat bodies or delivery codes."""
    if not is_configured():raise RuntimeError('Transactional email is not configured')
    base=os.environ.get('PUBLIC_BASE_URL','').strip().rstrip('/')
    parsed=urlsplit(base)
    if parsed.scheme not in ('https','http') or not parsed.netloc or parsed.username or parsed.password:raise ValueError('PUBLIC_BASE_URL must be an absolute URL')
    if os.environ.get('MARKETPLACE_MODE','development').lower()=='production' and parsed.scheme!='https':raise ValueError('HTTPS is required')
    message=EmailMessage();message['Subject']='SentryLoot — '+title;message['From']=_from_address();message['To']=address
    url=base+'/#notifications';description='Hisobingizda yangi bildirishnoma bor. Tafsilotlarni sayt ichida ko‘ring. Bildirishnomalarni profil sozlamalarida o‘chirishingiz mumkin.'
    message.set_content(title+'\n\n'+description+'\n'+url)
    message.add_alternative(_brand_html(description,title,display_name,[description],'Bildirishnomalarni ko‘rish',url,'Email xabarlari foydalanuvchi roziligi bilan yuboriladi.'),subtype='html');_deliver(message)


def _localized_email(address,name,language,kind,token='',reference='',status=''):
    """English/Russian service copy, without private order/chat contents."""
    if not is_configured():raise RuntimeError('Transactional email is not configured')
    ru=language=='ru'
    copy={
        'verify':('Подтвердите адрес электронной почты','Ссылка действует 24 часа.','Подтвердить email') if ru else ('Confirm your email address','This verification link is valid for 24 hours.','Confirm email'),
        'password_reset':('Сброс пароля','Откройте ссылку для изменения пароля. Она действует 30 минут.','Сбросить пароль') if ru else ('Reset your password','Open the link to change your password. It expires in 30 minutes.','Reset password'),
        'email_change':('Подтвердите новый email','Ссылка для подтверждения нового адреса действует 30 минут.','Подтвердить email') if ru else ('Confirm your new email','The link to confirm your new address expires in 30 minutes.','Confirm email'),
        'order':('Заказ обновлён','Статус заказа изменился. Проверьте текущие условия и следующий шаг на сайте.','Открыть заказы') if ru else ('Order updated','Your order status changed. Review its current terms and next step on the site.','View orders'),
        'security':('Безопасность аккаунта','Настройки безопасности аккаунта изменились. Если это были не вы, обратитесь в поддержку. Подробности доступны в аккаунте.','Открыть аккаунт') if ru else ('Account security','An account security setting changed. Contact support if this was not you. Review details in your account.','Open account'),
        'notification':('Новое уведомление','В аккаунте новое уведомление. Подробности доступны на сайте. Вы можете изменить настройки уведомлений в аккаунте.','Открыть уведомления') if ru else ('New notification','You have a new account notification. Open the site for details. You can change notification preferences in your account.','View notifications'),
    }
    if kind not in copy:raise ValueError('Unsupported email action')
    title,description,button=copy[kind]
    if kind in ('verify','password_reset','email_change'):url=action_link(kind,token)
    else:
        # Reuse the same validated origin handling as actionable email links.
        base=action_link('verify','origin-check').split('/#verify/')[0]
        url=base+{'order':'/#orders','security':'/#account','notification':'/#notifications'}[kind]
    greeting='Здравствуйте' if ru else 'Hello'
    footer=('Если вы не запрашивали эту ссылку, проигнорируйте письмо.' if ru else 'If you did not request this link, ignore this email.') if token else ('Пароли и секретные данные доставки не отправляются по email.' if ru else 'Passwords and private delivery details are never sent by email.')
    statuses={'pending_payment':('Ожидается оплата','Awaiting payment'),'paid':('Оплачено','Paid'),'awaiting_delivery':('Ожидается доставка','Awaiting delivery'),'delivered':('Доставлено','Delivered'),'completed':('Завершено','Completed'),'cancelled':('Отменено','Cancelled'),'refunded':('Возвращено','Refunded'),'disputed':('Спор','Disputed'),'under_review':('Проверяется','Under review')}
    facts=[(('Заказ' if ru else 'Order'),reference),(('Статус' if ru else 'Status'),statuses.get(status,(status,status))[0 if ru else 1])] if reference else None
    rendered=_brand_html(description,title,name,[description],button,url,footer,facts)
    replacements={
        'Salom, ':greeting+', ',
        'SentryLoot · Xavfsiz o‘yin bozori':'SentryLoot · '+('Игровая торговая площадка' if ru else 'Gaming marketplace'),
        'Agar tugma ishlamasa, ushbu manzilni brauzeringizga nusxalang:':'Если кнопка не работает, скопируйте адрес в браузер:' if ru else 'If the button does not work, copy this address into your browser:',
        'Bu avtomatik xizmat xabari. Javob berish shart emas.':'Автоматическое сервисное сообщение. Ответ не требуется.' if ru else 'Automated service message. No reply is required.',
        '<html>':'<html lang="'+language+'">',
    }
    for old,new in replacements.items():rendered=rendered.replace(old,new)
    message=EmailMessage();message['Subject']='SentryLoot — '+title+(' · '+reference if reference else '');message['From']=_from_address();message['To']=address
    message.set_content(greeting+', '+name+'.\n\n'+description+'\n'+('\n'.join(k+': '+v for k,v in facts)+'\n' if facts else '')+'\n'+url+'\n\n'+footer)
    message.add_alternative(rendered,subtype='html');_deliver(message)

def send_monitor_alert(address: str, workflow: str, run_url: str) -> None:
    """Operational alert with a fixed repository run URL; no logs, secrets or customer data."""
    if not is_configured():raise RuntimeError('Monitor email delivery is not configured')
    if address!='sentryloot@gamestorehub.com':raise ValueError('Unexpected monitor recipient')
    if not run_url.startswith('https://github.com/technolife360-dot/Marketplace/actions/runs/') or not run_url.rsplit('/',1)[-1].isdigit():raise ValueError('Unexpected monitor URL')
    workflow=' '.join(workflow.split())[:120]
    message=EmailMessage();message['Subject']='SentryLoot monitoring — '+workflow;message['From']=_from_address();message['To']=address
    description='Monitoring tekshiruvi xato bilan yakunlandi. Sababni GitHub run sahifasida tekshiring. Bu xabarda mijoz ma’lumotlari yoki maxfiy kalitlar yo‘q.'
    message.set_content(description+'\n\nWorkflow: '+workflow+'\n'+run_url)
    message.add_alternative(_brand_html(description,'Monitoring tekshiruvi',address,[description,workflow],'Tekshiruvni ochish',run_url,'Bu operatsion monitoring xabari.'),subtype='html');_deliver(message)

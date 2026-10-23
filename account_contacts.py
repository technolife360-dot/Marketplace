"""Private account phone numbers; never infer that a supplied number is verified."""
import re
import json
import time
import os

PREFIX = 'account_phone:'
VERIFIED_PREFIX = 'account_phone_verified:'
CHALLENGE_PREFIX = 'account_phone_challenge:'


def enabled():
    return os.environ.get('PHONE_VERIFICATION_ENABLED','false').strip().lower() == 'true'


def normalize_phone(value, country=None):
    import phonenumbers
    if not isinstance(value, str) or len(value) > 40:
        raise ValueError('Enter a phone number with country code, for example +60123456789.')
    value = re.sub(r'[ ().-]', '', value.strip())
    if country is not None and (not isinstance(country,str) or country not in phonenumbers.SUPPORTED_REGIONS):
        raise ValueError('Choose a valid phone country.')
    if not re.fullmatch(r'\+?[0-9]{6,15}', value):
        raise ValueError('Enter a phone number with country code, for example +60123456789.')
    try:
        number=phonenumbers.parse(value,country)
        if not phonenumbers.is_valid_number(number) or (country and not phonenumbers.is_valid_number_for_region(number,country)):
            raise ValueError('Enter a valid phone number for the selected country.')
        return phonenumbers.format_number(number,phonenumbers.PhoneNumberFormat.E164)
    except phonenumbers.NumberParseException:
        raise ValueError('Enter a valid phone number for the selected country.') from None


def countries():
    import phonenumbers
    return [{'country':region,'dial_code':'+'+str(phonenumbers.country_code_for_region(region))}
            for region in sorted(phonenumbers.SUPPORTED_REGIONS)]


def read(db, uid):
    row = db.execute('SELECT value FROM platform_config WHERE key=?', (PREFIX + uid,)).fetchone()
    return row['value'] if row else ''


def save(db, uid, phone):
    phone = normalize_phone(phone)
    db.execute('INSERT INTO platform_config(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=CURRENT_TIMESTAMP',
               (PREFIX + uid, phone))
    return phone


def verified(db, uid):
    row = db.execute('SELECT value FROM platform_config WHERE key=?', (VERIFIED_PREFIX+uid,)).fetchone()
    return bool(row and row['value'] == read(db, uid))


def store(db, key, value):
    db.execute('INSERT INTO platform_config(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=CURRENT_TIMESTAMP',
               (key, json.dumps(value, separators=(',', ':'))))


def challenge(db, uid):
    row = db.execute('SELECT value FROM platform_config WHERE key=?', (CHALLENGE_PREFIX+uid,)).fetchone()
    if not row: return None
    try:
        value = json.loads(row['value'])
        return value if value['expires_at'] > time.time() else None
    except (ValueError, TypeError, KeyError):
        return None

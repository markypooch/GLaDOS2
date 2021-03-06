import glados
import json
import sys
import requests
import urllib.parse


def translate(text, in_lang='auto', out_lang='en', verify_ssl=True):
    raw = False
    if out_lang.endswith('-raw'):
        out_lang = out_lang[:-4]
        raw = True

    headers = {
        'User-Agent': 'Mozilla/5.0' +
        '(X11; U; Linux i686)' +
        'Gecko/20071127 Firefox/2.0.0.11'
    }

    query = {
        "client": "gtx",
        "sl": in_lang,
        "tl": out_lang,
        "dt": "t",
        "q": text,
    }
    url = "http://translate.googleapis.com/translate_a/single"
    result = requests.get(url, params=query, timeout=40, headers=headers,
                          verify=verify_ssl).text

    if result == '[,,""]':
        return None, in_lang

    while ',,' in result:
        result = result.replace(',,', ',null,')
        result = result.replace('[,', '[null,')

    data = json.loads(result)

    if raw:
        return str(data), 'en-raw'

    try:
        language = data[2]  # -2][0][0]
    except:
        language = '?'

    return ''.join(x[0] for x in data[0]), language


class Translate(glados.Module):

    @glados.Module.command('tr', '[:en :fr] <phrase>', 'Translates phrase from :en to :fr')
    @glados.Module.command('translate', '', '')
    async def tr2(self, message, command):
        if not command:
            await self.provide_help('tr', message)
            return

        def langcode(p):
            return p.startswith(':') and (2 < len(p) < 10) and p[1:].isalpha()

        args = ['auto', 'en']

        for i in range(2):
            if ' ' not in command:
                break
            prefix, cmd = command.split(' ', 1)
            if langcode(prefix):
                args[i] = prefix[1:]
                command = cmd
        phrase = command

        if len(phrase) > 350:
            await self.client.send_message(message.channel, 'Phrase must be under 350 characters.')
            return

        if phrase.strip() == '':
            await self.client.send_message(message.channel, 'You need to specify a string for me to translate!')
            return

        src, dest = args
        if src != dest:
            msg, src = translate(phrase, src, dest)
            if msg:
                msg = urllib.parse.unquote(msg)
                msg = '"%s" (%s to %s, translate.google.com)' % (msg, src, dest)
            else:
                msg = 'The %s to %s translation failed, are you sure you specified valid language abbreviations?' % (src, dest)

            await self.client.send_message(message.channel, msg)
        else:
            await self.client.send_message(message.channel, 'Language guessing failed, so try suggesting one!')

import os
import random
import re
import collections
import enchant
from lzma import LZMAFile
from glados import Module, Permissions


class Quotes(Module):
    def __init__(self, server_instance, full_name):
        super(Quotes, self).__init__(server_instance, full_name)

        self.quotes_dir = os.path.join(self.local_data_dir, "quotes2")
        if not os.path.exists(self.quotes_dir):
            os.mkdir(self.quotes_dir)

        self.dictionaries = [
            enchant.Dict('en_US'),
            enchant.Dict('en_GB')
        ]

    # Intentionally don't match messages that contain newlines.
    @Permissions.spamalot
    @Module.rule('^(.*)$')
    async def record(self, message, match):
        self.__append_message(message.author, message.clean_content)
        return ()

    @Module.command('quote', '[user]', 'Dig up a quote the user (or yourself) once said in the past.')
    async def quote(self, message, args):
        target = message.author
        if args:
            members, roles, error = self.parse_members_roles(message, args, membercount=1, rolecount=0)
            if error:
                return await self.client.send_message(message.channel, error)
            target = members[0]

        quote = self.__get_random_message(target) or "{} hasn\'t delivered any quotes worth mentioning yet".format(target)
        await self.client.send_message(message.channel, '{0} once said: "{1}"'.format(target.name, quote))

    @Module.command('findquote', '<text> [user]', 'Dig up a quote the user once said containing the specified text.')
    async def findquote(self, message, args):
        args_parts = args.split(' ')
        if len(args_parts) == 1:
            target = message.author
            search_query = args.strip()
        else:
            members, roles, error = self.parse_members_roles(message, args_parts[-1])
            if error:
                target = message.author
                search_query = args.strip()
            else:
                search_query = ' '.join(args_parts[:-1]).strip()
                target = members.pop()

        quote = self.__get_random_message_matching(target, search_query) or "No quotes found matching \"{}\"".format(search_query)
        await self.client.send_message(message.channel, '{0} once said: "{1}"'.format(target.name, quote))

    @Module.command('quotestats', '[user]',
                           'Provide statistics on how many quotes a user (or yourself) has and '
                           'how intelligent he is')
    async def quotestats(self, message, content):
        if content == '':
            author = message.author
        else:
            members, roles, error = self.parse_members_roles(message, content)
            if error:
                return await self.client.send_message(message.channel, 'Unknown user.')
            else:
                author = members[0]

        lines = self.__load_all_messages(author)

        number_of_quotes = len(lines)
        average_quote_length = float(sum([len(quote) for quote in lines])) / float(number_of_quotes)

        words = [x.strip().strip('?.",;:()[]{}') for x in ' '.join(lines).split(' ')]
        words = [x for x in words if not x == '']
        number_of_words = len(words)
        average_word_length = float(sum([len(quote) for quote in words])) / float(number_of_words)

        frequencies = collections.Counter(words)
        common = "the be to of and a in that have I it for not on with he as you do at this but his by from they we say her she or an will my one all would there their what so up out if about who get which go me when make can like time no just him know take people into year your good some could them see other than then now look only come its over think also back after use two how our work first well way even new want because any these give day most us".split()
        vocab = len(self.filter_to_english_words(set(words)))
        most_common = ', '.join(['"{}" ({})'.format(w.replace('```', ''), i) for w, i in frequencies.most_common() if w not in common][:5])
        least_common = ', '.join(['"{}"'.format(w.replace('```', '')) for w, i in frequencies.most_common() if w.find('http') == -1][-5:])

        response = ('```\n{0} spoke {1} quotes\n'
                    'avg length       : {2:.2f}\n'
                    'words            : {3}\n'
                    'avg word length  : {4:.2f}\n'
                    'vocab            : {5}\n'
                    'Most common      : {6}\n'
                    'Least common     : {7}\n```').format(
            author.name, number_of_quotes, average_quote_length, number_of_words, average_word_length, vocab,
            most_common, least_common)

        await self.client.send_message(message.channel, response)

    @Module.command('grep', '<phrase> [User]', 'Find how many times a user has said a particular word. Case-insensitive')
    async def grep(self, message, content):
        content = content.split()
        if len(message.mentions):
            author = message.mentions[0]
            content.remove('@' + author.name)
        else:
            author = message.author


        lines = self.__load_all_messages(author)
        all_words = ' '.join(lines).lower()

        # have to use finditer if it's a phrase
        phrase = ' '.join(content).strip().lower()
        if len(content) > 1:
            found_count = len([m.start() for m in re.finditer(phrase, all_words)])
            total_count = len(all_words.split())
        else:
            found_count = 0
            total_count = 0
            for w in all_words.split():
                total_count += 1
                if re.sub(r'\W+', '', w.strip()) == re.sub(r'\W+', '', phrase):
                    found_count += 1

        if found_count == 0:
            response = '{} has never said "{}"'.format(author.name, phrase)
        else:
            response = '{0} has said "{1}" {2} times ({3:.2f}% of all words)'.format(author.name, phrase, found_count, found_count * 100.0 / total_count)
        await self.client.send_message(message.channel, response)

    @Module.command('zipf', '[user]', 'Plot a word frequency diagram of the user.')
    async def zipf(self, message, users):
        await self.client.send_message(message.channel, "Command not yet implemented! (Quotes is undergoing a rewrite)")

    def filter_to_english_words(self, words_list):
        return [word for word in words_list
                    if any(d.check(word) for d in self.dictionaries)
                    and (len(word) > 1 or len(word) == 1 and word in 'aAI')]

    def __quotes_file_name(self, author):
        return os.path.join(self.quotes_dir, author.id + '.txt.xz')

    def __remove_mentions(self, message):
        """
        Remove any mentions from the quote and replace them with actual member names
        """
        mentioned_ids = [x.strip('<@!>') for x in re.findall('<@!?[0-9]+>', message)]
        for mentioned_id in mentioned_ids:
            for member in self.server.members:
                if member.id == mentioned_id:
                    message = message.replace('<@{}>'.format(id), member.name).replace('<@!{}>'.format(id), member.name)
                    break
        return message.strip('<@!>')

    @staticmethod
    def __escape_message(message):
        return message.replace("\n", "\\n")

    @staticmethod
    def __unescape_message(message):
        return message.replace("\\n", "\n")

    def __append_message(self, author, message):
        with LZMAFile(self.__quotes_file_name(author), 'a') as f:
            message = self.__escape_message(message) + '\n'
            f.write(message.encode('utf-8'))

    def __load_all_messages(self, author):
        """
        Note: If the quotes file doesn't exist (can happen) this will throw.
        """
        with LZMAFile(self.__quotes_file_name(author), 'r') as f:
            lines = f.read().decode('utf-8').split('\n')
            return [self.__remove_mentions(self.__unescape_message(line)) for line in lines]

    def __get_random_message(self, author):
        try:
            return random.choice(self.__load_all_messages(author))
        except:
            return None

    def __get_random_message_matching(self, author, search_query):
        try:
            lines = self.__load_all_messages(author)
            lines = [x for x in lines if re.search(r'\b' + search_query + r'\b', x, re.IGNORECASE)]
            return random.choice(lines).replace(search_query, '**{}**'.format(search_query))
        except:
            return None

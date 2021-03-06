import glados
import os
import json
import dateutil.parser
from datetime import datetime, timedelta


class Permissions(glados.Permissions):

    def __init__(self, bot, full_name):
        super(Permissions, self).__init__(bot, full_name)

        # Create an entry in the global config file with the default command names
        permissions = self.settings.setdefault('permissions', {})
        permissions.setdefault('bot owner', '<please enter your discord ID>')
        permissions.setdefault('authorized servers', [])
        permissions.setdefault('server authorization', False)

        self.db_file = os.path.join(self.local_data_dir, 'permissions.json')
        self.db = dict()
        self.__load_db()

    def is_banned(self, member):
        return self.__is_member_still_marked_as(member, 'banned')

    def is_blessed(self, member):
        return self.__is_member_still_marked_as(member, 'blessed')

    def is_moderator(self, member):
        return self.__is_member_still_marked_as(member, 'moderator')

    def is_admin(self, member):
        return self.__is_member_still_marked_as(member, 'admin')

    def is_owner(self, member):
        return self.require_owner(member)

    def is_server_authorized(self):
        permissions = self.settings['permissions']
        return not permissions['server authorization'] or self.server.id in permissions['authorized servers']

    def require_moderator(self, member):
        return self.require_admin(member) or self.__is_member_still_marked_as(member, 'moderator')

    def require_admin(self, member):
        return self.require_owner(member) or self.__is_member_still_marked_as(member, 'admin')

    def require_owner(self, member):
        return member.id == self.settings['permissions']['bot owner']

    def get_ban_expiry(self, member):
        return self.__get_expiry(member, 'banned')

    def __compose_list_of_members_for(self, key):
        marked_members = list()
        for member in self.server.members:
            if self.__is_member_still_marked_as(member, key):
                expiry_date = self.db[key]['IDs'].get(member.id, None)
                if expiry_date is None:
                    for role in member.roles:
                        expiry_date = self.db[key]['roles'].get(role.name, None)
                        if expiry_date is not None:
                            break
                    if expiry_date is None:
                        glados.log('There\'s some weird shit going on here...')
                        continue

                if not expiry_date == 'never':
                    expiry_date = dateutil.parser.parse(expiry_date)
                    now = datetime.now()
                    if expiry_date > now:
                        time_to_expiry = expiry_date - now
                        time_to_expiry = '{0:.1f} hour(s)'.format(time_to_expiry.seconds / 3600.0)
                    else:
                        time_to_expiry = '0 hour(s)'
                else:
                    time_to_expiry = 'forever'
                marked_members.append((member, time_to_expiry))

        return marked_members

    @glados.Module.command('modlist', '', 'Displays which users have privileges')
    async def modlist(self, message, content):
        mod_list = self.__compose_list_of_members_for('moderator')
        admin_list = self.__compose_list_of_members_for('admin')
        owner = self.server.get_member(self.settings['permissions']['bot owner'])

        strings = ['**Moderators:**']
        strings += ['  + ' + x[0].name + ' for {}'.format(x[1]) for x in mod_list]
        strings += ['**Administrators:**']
        strings += ['  + ' + x[0].name + ' for {}'.format(x[1]) for x in admin_list]
        strings += ['**Owner:** {}'.format(owner)]

        for msg in self.pack_into_messages(strings):
            await self.client.send_message(message.channel, msg)

    @glados.Module.command('banlist', '', 'Displays which users are banned')
    async def banlist(self, message, content):
        banned = self.__compose_list_of_members_for('banned')
        if len(banned) > 0:
            strings = ['**Banned Users**']
            strings += ['  + ' + x[0].name + ' for {}'.format(x[1]) for x in banned]
        else:
            strings = ['No one is banned.']

        for msg in self.pack_into_messages(strings):
            await self.client.send_message(message.channel, msg)

    @glados.Module.command('blesslist', '', 'Displays which users are blessed')
    async def blesslist(self, message, content):
        blessed = self.__compose_list_of_members_for('blessed')
        if len(blessed) > 0:
            strings = ['**Blessed Users**']
            strings += ['  + ' + x[0].name + ' for {}'.format(x[1]) for x in blessed]
        else:
            strings = ['No one is blessed.']

        for msg in self.pack_into_messages(strings):
            await self.client.send_message(message.channel, msg)

    @glados.Permissions.moderator
    @glados.Module.command('ban', '<user/role> [user/role...] [hours=24]', 'Blacklist the specified user(s) or '
                           'roles from using the bot for the specified number of hours. The default number of hours is '
                           '24. Specifying a value of 0 will cause the user to be perma-banned. The ban is based on '
                           'user ID.')
    async def ban_command(self, message, content):
        members, roles, duration, error = self.__parse_members_roles_duration(message, content, 24)
        if error:
            await self.client.send_message(message.channel, error)
            return

        # If you are a moderator, then you can't ban admins
        if self.is_moderator(message.author):
            filtered_members = list()
            send_error = False
            for member in members:
                if self.is_admin(member):
                    for role in member.roles:
                        try:
                            roles.remove(role)
                        except ValueError:
                            pass
                    send_error = True
                else:
                    filtered_members.append(member)
            members = filtered_members
            if send_error:
                await self.client.send_message(message.channel, 'Moderators can\'t ban admins')

        await self.client.send_message(message.channel,
                self.__mark_command(members, roles, duration, 'banned'))

    @glados.Permissions.moderator
    @glados.Module.command('unban', '<user/role> [user/role...]', 'Allow a banned user(s) to use the bot again')
    async def unban_command(self, message, content):
        members, roles, duration, error = self.__parse_members_roles_duration(message, content, 0)
        if error:
            await self.client.send_message(message.channel, error)
            return

        await self.client.send_message(message.channel,
                self.__unmark_command(members, roles, 'banned'))

    @glados.Permissions.moderator
    @glados.Module.command('bless', '<user/role> [user/role...] [hours=1]', 'Allow the specified user to evade the '
                           'punishment system for a specified number of hours. Specifying 0 means forever. This '
                           'allows the user to excessively use the bot without consequences.')
    async def bless_command(self, message, content):
        members, roles, duration, error = self.__parse_members_roles_duration(message, content, 1)
        if error:
            await self.client.send_message(message.channel, error)
            return

        await self.client.send_message(message.channel,
                self.__mark_command(members, roles, duration, 'blessed'))

    @glados.Permissions.moderator
    @glados.Module.command('unbless', '<user/role> [user/role...]', 'Removes a user\'s blessing so he is punished '
                           'for excessive use of the authorized serversbot again.')
    async def unbless_command(self, message, content):
        members, roles, duration, error = self.__parse_members_roles_duration(message, content, 0)
        if error:
            await self.client.send_message(message.channel, error)
            return

        await self.client.send_message(message.channel,
                self.__unmark_command(members, roles, 'blessed'))

    @glados.Permissions.admin
    @glados.Module.command('mod', '<user/role> [user/role...] [hours=0]', 'Assign moderator status to a user or role.'
                           ' Moderators are able to bless, unbless, ban or unban users, but they cannot use any admin '
                           'commands.')
    async def mod_command(self, message, content):
        members, roles, duration, error = self.__parse_members_roles_duration(message, content, 0)
        if error:
            await self.client.send_message(message.channel, error)
            return

        for member in members:
            if self.__is_member_still_marked_as(member, 'admin') and not self.is_owner(message.author):
                return await self.client.send_message(message.channel, 'Can\'t demote admins to moderators.')

        self.__unmark_command(members, roles, 'admin')
        await self.client.send_message(message.channel,
                self.__mark_command(members, roles, duration, 'moderator'))

    @glados.Permissions.admin
    @glados.Module.command('unmod', '<user/role> [user/role]', 'Removes moderator status from users or roles.')
    async def unmod_command(self, message, content):
        members, roles, duration, error = self.__parse_members_roles_duration(message, content, 0)
        if error:
            await self.client.send_message(message.channel, error)
            return

        await self.client.send_message(message.channel,
                self.__unmark_command(members, roles, 'moderator'))

    @glados.Permissions.owner
    @glados.Module.command('admin', '<user/role> [user/role] [hours=0]', 'Assign admin status to a user or role. '
                           'Admins can do everything moderators can, including major bot internal stuff (such as '
                           'reloading the config, managig databases, etc.) They can also assign moderator status to '
                           'people. Only give this to people you really trust.')
    async def admin_command(self, message, content):
        members, roles, duration, error = self.__parse_members_roles_duration(message, content, 0)
        if error:
            await self.client.send_message(message.channel, error)
            return

        self.__unmark_command(members, roles, 'moderator')
        msg = self.__mark_command(members, roles, duration, 'admin')
        await self.client.send_message(message.channel, msg)

    @glados.Permissions.owner
    @glados.Module.command('unadmin', '<user/role> [user/role]', 'Removes admin status from users or roles.')
    async def unadmin_command(self, message, content):
        members, roles, duration, error = self.__parse_members_roles_duration(message, content, 0)
        if error:
            await self.client.send_message(message.channel, error)
            return

        await self.client.send_message(message.channel,
                self.__unmark_command(members, roles, 'admin'))

    @glados.Permissions.owner
    @glados.Module.command('addserver', '', 'Allows the bot to interact with this server. If this is not set, then the '
                           'bot will simply ignore all queries sent to it.')
    async def addserver(self, message, content):
        authd_servers = self.settings['permissions']['authorized servers']
        if message.server.id not in authd_servers:
            authd_servers.append(message.server.id)
            await self.client.send_message(message.channel, 'This server ({}) is now authorized to use this bot.'.format(
                message.server.name))
        else:
            await self.client.send_message(message.channel, 'Server already authorized')

    @glados.Permissions.owner
    @glados.Module.command('rmserver', '[server index]', 'Remove the bot from a server. The bot doesn\'t leave but it '
                           'will stop responding to queries.')
    async def rmserver(self, message, content):
        if content:
            servers = list(self.client.servers)
            try:
                index = int(content)
                if index > len(servers) or index < 1:
                    raise ValueError('Index out of range')
            except ValueError as e:
                await self.client.send_message(message.channel, 'Error: {}'.format(e))
                return
            server = servers[index - 1]
        else:
            server = message.server

        try:
            self.settings['permissions']['authorized servers'].remove(server.id)
            await self.client.send_message(message.channel, 'Server ({}) removed.'.format(server.name))
        except ValueError:
            await self.client.send_message(message.channel, 'Server already removed.'.format(server.name))

    @glados.Permissions.owner
    @glados.Module.command('serverlist', '', 'List all servers the bot has joined')
    async def serverlist(self, message, content):
        servers_auths = [(server.name, server.id in self.settings['permissions']['authorized servers'])
                         for server in self.client.servers]
        strings = list(' {}. {}: {}'.format(index+1, serv_auth[0], 'yes' if serv_auth[1] else '**no**')
                       for index, serv_auth in enumerate(servers_auths))

        if not self.settings['permissions']['server authorization']:
            strings += ['Note: Serverauth is not enabled, so all servers will be able to use your bot anyway. You can '
                        'enable serverauth with {}serverauth'.format(self.command_prefix)]

        strings = self.pack_into_messages(strings)
        for msg in strings:
            await self.client.send_message(message.channel, msg)

    @glados.Permissions.owner
    @glados.Module.command('serverauth', '<enable|disable>', 'Enable or disable the server authorization feature')
    async def serverauth(self, message, content):
        if content == 'enable':
            self.settings['permissions']['server authorization'] = True
            await self.client.send_message(message.channel, 'Enabled. Your bot will ignore all messages if not authorized')
        elif content == 'disable':
            self.settings['permissions']['server authorization'] = False
            await self.client.send_message(message.channel, 'Disabled. Anyone who adds your bot to their server can use it')
        else:
            await self.provide_help('serverauth', message)

    def __parse_members_roles_duration(self, message, content, default_duration):
        # Default duration is 24 hours
        args = content.split()
        if len(args) < 2:
            duration = default_duration
        else:
            try:
                duration = float(args[-1])
            except ValueError:
                duration = default_duration

        members, roles, error = self.parse_members_roles(message, content)
        return members, roles, duration, error

    def __mark_command(self, members, roles, duration, key):
        if duration > 0:
            expiry_date = datetime.now() + timedelta(duration / 24.0)
        else:
            expiry_date = 'forever'
        for member in members:
            self.__mark_member_as(member, key, duration_h=duration)
        for role in roles:
            self.__mark_role_as(role.name, key, duration_h=duration)

        # Generate message to send to channel
        users_marked = ', '.join([x.name for x in members])
        roles_marked = ', '.join([x.name for x in roles])
        msg = ''
        if users_marked:
            msg = 'User{} "{}"'.format('s' if len(members) > 1 else '', users_marked)
        if roles_marked:
            if users_marked:
                msg += ' and '
            msg += 'Role{} "{}" '.format('s' if len(roles) > 1 else '', roles_marked)
        msg += ' {} {} until {}'.format(
            'are' if len(members) + len(roles) > 1 else 'is', key, expiry_date)
        return msg

    def __unmark_command(self, members, roles, key):
        unmarked = list()
        for member in members:
            if not self.__is_member_still_marked_as(member, key):
                continue
            self.__unmark_member(member, key)
            unmarked.append(member)
        for role in roles:
            self.__unmark_role(role.name, key)
            unmarked.append(role)

        return '"{}": No longer {}'.format(', '.join(x.name for x in unmarked), key)

    def __load_db(self):
        if os.path.isfile(self.db_file):
            self.db = json.loads(open(self.db_file).read())

        # make sure all keys exists
        def add_default(key):
            self.db.setdefault(key, {
                'IDs': {},
                'roles': {}
            })
        add_default('banned')
        add_default('blessed')
        add_default('moderator')
        add_default('admin')

    def __save_db(self):
        with open(self.db_file, 'w') as f:
            s = json.dumps(self.db, indent=2, sort_keys=True)
            f.write(s)

    def __is_member_still_marked_as(self, member, key):
        try:
            expiry_dates = [
                ('IDs', member.id, self.db[key]['IDs'][member.id])
            ]
        except KeyError:
            member_role_names = set(x.name for x in member.roles)
            key_role_names = set(self.db[key]['roles'])
            expiry_dates = [('roles', x, self.db[key]['roles'][x])
                            for x in member_role_names.intersection(key_role_names)]
            if len(expiry_dates) == 0:
                return False

        # NOTE: expiry_dates contains a list of tuples, where each tuple is:
        #   (type_key, item_key, expiry_date)
        # This is to match the JSON structure so keys can be deleted easily. The structure is:
        #   key : {
        #     type_key1 : {
        #       item_key1 : expiry_date,
        #       item_key2 : expiry_date
        #     },
        #     type_key2: {
        #       item_key1 : expiry_date
        #       item_key2 : expiry_date
        #     }
        #   }

        expiry_dates_len = len(expiry_dates)
        for type_key, item_key, expiry_date in expiry_dates:
            if expiry_date == 'never':
                continue
            if datetime.now().isoformat() > expiry_date:
                self.db[key][type_key].pop(item_key)
                expiry_dates_len -= 1

        if expiry_dates_len < len(expiry_dates):
            self.__save_db()

        if expiry_dates_len == 0:
            return False
        return True

    def __mark_member_as(self, member, key, duration_h=0):
        if duration_h > 0:
            expiry_date = datetime.now() + timedelta(duration_h / 24.0)
            expiry_date = expiry_date.isoformat()
        else:
            expiry_date = 'never'
        self.db[key]['IDs'][member.id] = expiry_date
        self.__save_db()

    def __mark_role_as(self, role_name, key, duration_h=0):
        if duration_h > 0:
            expiry_date = datetime.now() + timedelta(duration_h / 24.0)
            expiry_date = expiry_date.isoformat()
        else:
            expiry_date = 'never'
        self.db[key]['roles'][role_name] = expiry_date
        self.__save_db()

    def __unmark_member(self, member, key):
        self.db[key]['IDs'].pop(member.id, None)
        self.__save_db()

    def __unmark_role(self, role_name, key):
        self.db[key]['roles'].pop(role_name, None)
        self.__save_db()

    def __get_expiry(self, member, key):
        try:
            return self.db[key]['IDs'][member.id]
        except KeyError:
            banned_roles = self.db['banned']['roles']
            for role in member.roles:
                expiry = banned_roles.get(role.name, '')
                if expiry:
                    return expiry
        raise RuntimeError('Tried to get expiry on a member that has no expiry')

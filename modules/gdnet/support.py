import glados


class GDNIsOffline(glados.Module):
    @glados.Module.rule(r'^\!profile.*$')
    @glados.Module.rule(r'^\!claim$')
    @glados.Module.rule(r'^\!rules$')
    @glados.Module.rule(r'^\!help$')
    async def respond_if_down(self, message, match):
        Hodge_id = '109587405673091072'
        GDN_id = '188103830360162309'
        GDN_member = message.server.get_member(GDN_id)
        Hodge_member = message.server.get_member(Hodge_id)
        if GDN_member is None or isinstance(GDN_member, str):  # can be a string or none if the member is not found
            return tuple()
        if str(GDN_member.status) == 'offline':
            await self.client.send_message(message.channel, '{} is offline because {} didn\'t feed the hamster'.format(GDN_member.mention, Hodge_member.mention))
        return tuple()

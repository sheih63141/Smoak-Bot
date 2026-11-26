import asyncio, discord, ticket_gate
TOK=[l.split("=",1)[1].strip() for l in open(".env") if l.startswith("DISCORD_TOKEN")][0]
async def main():
    intents=discord.Intents.none(); intents.guilds=True
    c=discord.Client(intents=intents); ev=asyncio.Event()
    @c.event
    async def on_ready(): ev.set()
    await c.login(TOK); t=asyncio.create_task(c.connect(reconnect=False))
    try:
        await asyncio.wait_for(ev.wait(),60)
        print("=== догоняю висящие клики ===")
        await ticket_gate.sweep_panel(c)
        g=c.get_guild(1568607492991353053)
        for nm,cid in (("🎫 ТИКЕТЫ","1568866419100094474"),("📋 ОБРАЩЕНИЯ","1568867246426824846"),("📝 ЗАЯВКИ","1568867318514057236")):
            kids=[x for x in g.text_channels if x.category and x.category.id==cid]
            print(f"  {nm}: {[(k.name,k.topic) for k in kids]}")
        panel=discord.utils.get(g.text_channels,name=ticket_gate.PANEL_CHANNEL)
        msg=await panel.fetch_message(1568675272876753049)
        print("  реакции на панели:",[(str(r.emoji),r.count) for r in msg.reactions])
    finally:
        await c.close(); t.cancel()
asyncio.run(main())

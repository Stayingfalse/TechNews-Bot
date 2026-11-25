# raosanta.uk: the 2026 season

The plan is [`santa_season/2026.json`](../santa_season/2026.json); this page shows how it plays out if the channel
starts on Thu 26 Nov (one post a day, at a time that moves two hours earlier each day). If it starts later,
the first few drop out and the rest keep their dates. Voiced: tutorials and pitches. `{...}` are the site's
live figures, filled in when each video is made.

| When | Format | Audience | Hook | Voice |
|---|---|---|---|---|
| Thu 26 Nov 21:30 | update |  | Gifting opens {season.opensOn} |  |
| Fri 27 Nov 20:00 | update |  | Gifting is open |  |
| Sat 28 Nov 17:30 | pitch | workplace | Remote team? Nobody needs a home address. | Lily |
| Sun 29 Nov 15:30 | tutorial |  | How to be someone's Santa | Lily |
| Mon 30 Nov 13:45 | pitch | friends | Hate the Secret Santa draw? | Lily |
| Tue 01 Dec 11:00 | quiz |  | Only real Christmas film fans get 2 out of 2 |  |
| Wed 02 Dec 10:00 | pitch | community | Run a Discord server? | Archie |
| Thu 03 Dec 07:30 | tutorial |  | Who sees what? | Lily |
| Fri 04 Dec 21:30 | update |  | Week one: thank you |  |
| Sat 05 Dec 20:00 | tutorial |  | Christmas for your Discord server | Lily |
| Sun 06 Dec 17:30 | quiz |  | A Christmas Carol: 2 out of 2? |  |
| Mon 07 Dec 15:30 | pitch | workplace | Christmas for a team that never meets? | Lily |
| Tue 08 Dec 13:45 | tutorial |  | Start a friends group | Lily |
| Wed 09 Dec 11:00 | quiz |  | Christmas songs: 2 out of 2? |  |
| Thu 10 Dec 10:00 | tutorial |  | Sent a gift? Tell us | Lily |
| Fri 11 Dec 07:30 | quiz |  | Christmas food: 2 out of 2? |  |
| Sat 12 Dec 21:30 | update |  | Order by {season.lastOrderOn} |  |
| Sun 13 Dec 20:00 | pitch |  | Some wishlists have no gifts yet | Lily |
| Mon 14 Dec 17:30 | quiz |  | Grinches and ghosts: 2 out of 2? |  |
| Tue 15 Dec 15:30 | tutorial |  | Got a gift? Say thanks | Lily |
| Wed 16 Dec 13:45 | quiz |  | Christmas plants: 2 out of 2? |  |
| Thu 17 Dec 11:00 | pitch | community | Mods: Christmas for the whole server | Archie |
| Fri 18 Dec 10:00 | update |  | The thank-yous are in |  |
| Sat 19 Dec 07:30 | quiz |  | Santa's reindeer: 2 out of 2? |  |
| Sun 20 Dec 21:30 | tutorial |  | Gifted everyone you picked up? | Lily |
| Mon 21 Dec 21:00 | quiz |  | Christmas films: 2 out of 2? |  |
| Tue 22 Dec 17:30 | pitch |  | Missed the last order day? | Lily |
| Wed 23 Dec 15:30 | tutorial |  | Organisers: make a Wall of Kindness | Lily |
| Thu 24 Dec 13:45 | quiz |  | Christmas Eve quiz: 2 out of 2? |  |
| Fri 25 Dec 11:00 | update |  | Merry Christmas from raosanta.uk |  |
| Sat 26 Dec 10:00 | quiz |  | Boxing Day quiz: 2 out of 2? |  |
| Sun 27 Dec 07:30 | quiz |  | Is it a Christmas film? 2 out of 2 |  |
| Mon 28 Dec 21:30 | update |  | What a Christmas |  |
| Tue 29 Dec 20:00 | quiz |  | Where did Santa come from? |  |
| Wed 30 Dec 17:30 | tutorial |  | Still need to say thank you? | Lily |
| Thu 31 Dec 15:30 | quiz |  | Leftovers quiz: 2 out of 2? |  |
| Fri 01 Jan 13:45 | update |  | Gifting closes {season.closesOn} |  |
| Sat 02 Jan 11:00 | quiz |  | Christmas classics: 2 out of 2? |  |
| Sun 03 Jan 10:00 | tutorial |  | Did your gift arrive? | Lily |
| Mon 04 Jan 07:30 | pitch | friends | Next year, skip the draw | Lily |
| Tue 05 Jan 21:30 | quiz |  | Christmas traditions: 2 out of 2? |  |
| Wed 06 Jan 20:00 | update |  | Last day of the season |  |
| Thu 07 Jan 17:30 | update |  | That's a wrap for {season.year} |  |

Not used if it starts on 26 Nov (spares and fillers, used when something above can't go out): `tutorial-share-wishlist-2026`, `quiz-filler-carols`, `quiz-filler-nativity`, `quiz-filler-snow`, `quiz-filler-twelve`.

Nothing is booked after 7 January. To change anything, edit the JSON (each item: `spec`, and optionally `from`
and `until` as UK dates) and deploy: the server books 3 days ahead, so edits reach every post not yet booked.

---
name: dan-project-glossary
description: Shared vocabulary for a project, kept in its glossary as words get settled. Load when a word is carrying two meanings, when the user asks what a term means, when you are about to give something a name of your own, when a rename is decided, when you are handed a project's creative brief or other founding document, or before editing a GLOSSARY.md or CONTEXT.md.
---

# Project glossary

A project's glossary is how the people on it, and every agent they work with, end up meaning the same thing by the same word. Nobody sits down to write it. It grows one term at a time, in passing, at the moment a word gets settled in conversation. Your part is to notice that moment, settle the word in a sentence, and record it before the conversation moves on.

## The moments

- **One word, two meanings.** The user's use of a term and the glossary's, or the code's, or their own use ten messages ago, do not match. Say which two meanings are live and ask which one the word keeps: "The glossary has _screen_ as one route; you seem to mean one step inside a route. Which is it?" Ask one question, and only when you cannot tell from what they have said. When you can tell, the word still has two meanings on this project and the glossary shows one of them: record the other, as its own entry or as a line on the existing entry that tells the two apart.
- **"What does that mean?"** The user asks what a term refers to, or says a message lost them because of one. Answer in a sentence, then treat the word as unsettled: it was not shared, so it gets an entry.
- **A name of your own.** Before you label something, look for the word the project already uses. If there is none and you coin one, say it is yours and define it where you first use it. Record it only once the user starts using it too: a label that lives in one session is not vocabulary.
- **A rename.** The user decides a thing is now called something else. The new word gets the entry and the old one goes under _Avoid_.
- **A founding document.** You are handed the project's creative brief, scope or content outline, and the repo has no glossary yet. Seed one from it: every thing the document names that the team will go on saying (the screens, the parts of the experience, the roles), each with the meaning the document gives it. Where it shows two groups using different words for one thing, or one word used two ways, keep the word of whoever the document says has the final say and list the other under _Avoid_; ask only where it gives no way to choose.

Asked to define a project's terms in one sitting, do the same across the repo: write the entries you are sure of, then ask about the rest, through a grilling skill where the session has one and otherwise in rounds of about five questions grouped by theme.

## Recording it

Each moment ends with the glossary changed, except a name of your own that the user has not taken up. It is finished when the file says what you have just told the user, unless they have asked you to leave files alone.

1. Find the project's glossary: a root `GLOSSARY.md`, the files a `GLOSSARY-MAP.md` lists, or the `CONTEXT.md` or `docs/GLOSSARY.md` the project already keeps its terms in. Check for each by its exact name, now, even if you looked before loading this skill: a wildcard such as `GLOSSARY*` that matches nothing makes the shell drop the whole listing, and the files that do exist go with it. Where the repo keeps several, pick the one the topic belongs to. A glossary under another of those names keeps its name and place. Only when the project has none, create `GLOSSARY.md` at the root with this first term.
2. Add or correct the entry in the shape the file already uses. For a new file, use [GLOSSARY-FORMAT.md](./GLOSSARY-FORMAT.md): the word, one or two sentences on what it is, and the words to avoid for it. A glossary says what a word means on this project; how the thing is built belongs in the code and its docs.
3. Tell the user in one line what you recorded and where, so the edit is theirs to keep or drop with the rest of the work.
4. Use the settled word from then on, in what you say and in any issue, PR or doc you write this session.

When the retired word is still spread through the repo's issues, docs or code, say roughly how many places and leave the sweep for the user to ask for.

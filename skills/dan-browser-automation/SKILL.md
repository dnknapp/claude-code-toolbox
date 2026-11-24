---
name: dan-browser-automation
description: "How to drive Chrome through claude-in-chrome so what you see is real: confirm the tab is awake, give every evaluate a deadline, navigate with the tool, scrub animations to verify. Load at the start of any claude-in-chrome work, and before diagnosing anything animated, measured, or clicked through the browser."
---

Chrome throttles a tab that isn't visible, and the user's Chrome usually sits in a different Space from the terminal, so the automation tab is usually **asleep**: no `requestAnimationFrame`, no `ResizeObserver` delivery. Screenshots keep succeeding, so an asleep tab imitates a real bug convincingly. Everything below keeps you working against an awake tab, or knowing that you aren't.

## 1. Open the tab

`tabs_context_mcp` with `createIfEmpty: true`, then `navigate`. The same call reopens the tab group after you close your last tab, when `tabs_create_mcp` fails. Serve scratch HTML over http (`python3 -m http.server` in the scratchpad); the extension navigates http(s) only.

## 2. Confirm the tab is awake

Run this before measuring, clicking, or judging anything animated, and again after a resize or a new tab, since a window can go hidden mid-session:

```js
await new Promise(r => { let ok = false; requestAnimationFrame(() => { ok = true; r('awake') }); setTimeout(() => r(ok ? 'awake' : 'asleep: ' + document.visibilityState), 500) })
```

Awake: carry on. Asleep: say so and stop; bringing Chrome to the active Space is input only the user can provide. Signs you are reading an asleep tab: GSAP tweens at `progress() === 0`, an r3f canvas showing its last frame or nothing, observer-sized layouts stuck at their initial value so `getBoundingClientRect` is degenerate and clicks land on nothing, and a console `AbortError` about background media paused to save power.

To verify an outcome from an asleep tab, **scrub** instead of waiting: `tween.progress(1)`; for r3f `setFrameloop('never')` then `advance(performance.now())` (`invalidate()` still ends in a rAF). Anything not rAF-driven still works, so `el.scrollLeft = n` positions the page and fires real scroll handlers.

## 3. Evaluate with a deadline

Every awaited promise inside `javascript_tool` carries a timeout, and loops run a few iterations per call. An evaluate that reaches the 45 s CDP timeout keeps running in the page and **jams** the tab: every later call times out and navigating does not clear it. Close the jammed tab and open a fresh one. Reload or change URL with `navigate`, then evaluate; `location.reload()` inside an evaluate ends the call.

## 4. Click by reference

Click `find` references. When a click needs coordinates after `resize_window`, scale page-derived values by `screenshotWidth / window.innerWidth`, because the click tool works in screenshot space and an unscaled click lands ~7% off on a neighbor, silently.

## Trello checklists

Read from the logged-in tab with `fetch('/1/cards/<id>/checklists?checkItems=all&checkItem_fields=name,state')`; tick by clicking the `input[type=checkbox]` whose `aria-label` starts with the item name; confirm with the same fetch. The items are absent from `get_page_text`, and from `find` until the card dialog has rendered.

# Amazon Time Cost

A Chrome extension that shows Amazon prices as the **hours and minutes of work** required to afford each item, based on your take-home hourly wage.

## Why

Money is abstract; hours of your life are not. A $200 pair of headphones is "8 hours" of your life. A $1,500 laptop is nearly two full work weeks. Reframing prices as time grounds purchasing decisions in the one resource you can't get more of, and changes the gut-level math behind impulse buys.

## What it does

Finds every price on amazon.com and appends a time badge next to it:

```
$49.99 · 2h 30m
```

A toggle in the popup hides the dollar amount entirely, so the time becomes the only thing you see.

The extension re-runs as you scroll, switch pages, or expand product carousels — Amazon loads prices dynamically, and a `MutationObserver` keeps the badges in sync.

## Install

1. Clone this repo
2. Open `chrome://extensions` in Chrome
3. Toggle **Developer mode** on (top right)
4. Click **Load unpacked** and select this folder
5. Click the extension icon in the toolbar, enter your take-home hourly wage, and save
6. Visit any amazon.com page — prices will show their time equivalent

## Limitations (v1.0.1)

- amazon.com only — other regions are skipped to avoid currency-conversion ambiguity
- Price ranges (e.g. `$10 – $20`) show the time for the lower bound only
- "Free" or non-numeric prices are skipped
- No custom icon yet — Chrome shows a generic puzzle piece

## Running the tests

The pure logic (price parsing, hour math, time formatting) is covered by unit tests. They run via Apple's built-in JavaScript engine, so no Node install is required:

```
/System/Library/Frameworks/JavaScriptCore.framework/Versions/Current/Helpers/jsc lib.js tests/test.js
```

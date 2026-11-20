---
title: From Idea to TestFlight in One Day
date: 2026-11-20
time: "19:10"
slug: idea-to-testflight-in-one-day
lang: en
translation_of: ko
description: On 19 November we went from an empty repository to the first TestFlight build of 오늘 어때. Here is what we cut to make that possible.
category: process
---

On 19 November, 오늘 어때 went from an empty project to a first build on TestFlight. The point of the day was not to ship everything. It was to ship one complete loop, so we could see whether the game works before we add more.

## The loop we kept

The first build has one path: home, a partner, five scenes, a choice at each scene, an affection bar, an ending, and a collection of postcards. Every other idea waited until this path worked from start to finish.

- **Home** shows today's scene.
- **Partner** sets who you are going out with.
- **Five scenes** each offer a choice that moves the story.
- **Ending and collection** keep the stories you finished as postcards.

## What we cut

- Extra languages. The first build shipped Korean and English. Other languages fall back to English until we translate them.
- Extra scenes. The first build used a small set so the flow could be tested end to end.
- Polish that did not change the loop. We fixed what blocked a tester and left the rest for the next pass.

## What we learned

A one-day build is mostly about deciding what not to do. Each cut made the next step smaller, and the build was real enough to test on a phone the same day.

The next post covers the scenes we shipped in version 1.1.

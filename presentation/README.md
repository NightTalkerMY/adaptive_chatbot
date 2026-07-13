# Adaptive Chat demo slides

Open `demo-slides.html` in a browser. Use the left/right arrow keys, Space,
Page Up, or Page Down to navigate.

The deck contains eight lightweight slides designed for approximately six to
eight minutes of explanation followed by a live application demo.

## Suggested timing

1. Title and task objective — 45 seconds
2. Requirements — 60 seconds
3. Architecture — 60 seconds
4. Streaming contract — 75 seconds
5. Conversation memory — 60 seconds
6. Adaptive interface — 45 seconds
7. Testing methodology — 75 seconds
8. Live-demo plan and transition — 30 seconds

## Live-demo prompts

Start with:

> Write a Python function that merges two sorted lists.

Then prove session memory with:

> What is the time complexity of that function, and why?

Switch modes with:

> Now write a short poem inspired by the idea of merging two paths.

Finish by refreshing the browser to show persisted history, then run:

```bash
cd backend
.venv/bin/python -m pytest tests/ -v
```

## Presentation tips

- Say "provider response chunks" when explaining Gemini's streaming boundary.
- Explain that FastAPI forwards each chunk immediately through SSE.
- Emphasize that the tests exercise the real API and database while replacing
  only the external Gemini dependency.
- Keep the live demo under seven minutes so the complete session stays within
  the requested 15–20 minute window.

To export a PDF, open the deck in a browser and use Print → Save as PDF. The
print stylesheet places each slide on its own 16:9 page.

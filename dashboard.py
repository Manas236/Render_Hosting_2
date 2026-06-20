from datetime import datetime
from flask import Blueprint, render_template_string
import config
from helpers import require_login

dashboard_bp = Blueprint('dashboard_bp', __name__)

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Newsband — Dashboard</title>
  <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,700;0,900;1,700&family=IBM+Plex+Mono:wght@400;500&family=Source+Sans+3:wght@300;400;600&display=swap" rel="stylesheet">
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    :root { --ink: #0a0a0a; --paper: #f4f0e8; --accent: #c8102e; --mid: #5a5247; --rule: #1a1a1a; --faint: #e0dbd0; }
    body { background-color: var(--paper); background-image: repeating-linear-gradient(0deg, transparent, transparent 27px, var(--faint) 27px, var(--faint) 28px); min-height: 100vh; display: flex; align-items: center; justify-content: center; font-family: 'Source Sans 3', sans-serif; }
    .page-wrap { width: 100%; max-width: 580px; padding: 24px; }
    .masthead { text-align: center; border-top: 4px solid var(--rule); border-bottom: 1px solid var(--rule); padding: 14px 0 12px; margin-bottom: 6px; position: relative; }
    .masthead::before { content: ''; display: block; height: 2px; background: var(--accent); margin-bottom: 12px; }
    .masthead-logo { max-width: 260px; max-height: 80px; width: auto; height: auto; object-fit: contain; display: block; margin: 0 auto; }
    .masthead-tagline { font-family: 'IBM Plex Mono', monospace; font-size: 0.62rem; letter-spacing: 0.18em; color: var(--mid); text-transform: uppercase; margin-top: 10px; }
    .dateline { font-family: 'IBM Plex Mono', monospace; font-size: 0.6rem; color: var(--mid); text-align: center; padding: 4px 0; border-bottom: 1px solid var(--rule); margin-bottom: 32px; letter-spacing: 0.08em; display: flex; justify-content: space-between; align-items: center; }
    .dateline a { color: var(--accent); text-decoration: none; font-weight: 600; letter-spacing: 0.1em; }
    .dateline a:hover { text-decoration: underline; }
    .card { background: #fff; border: 1px solid #c8c2b5; padding: 36px 40px 40px; box-shadow: 4px 4px 0 var(--ink); animation: slideUp 0.5s cubic-bezier(0.22, 1, 0.36, 1) both; }
    @keyframes slideUp { from { opacity: 0; transform: translateY(20px); } to   { opacity: 1; transform: translateY(0); } }
    .card-headline { font-family: 'Playfair Display', serif; font-size: 1.45rem; font-weight: 700; color: var(--ink); margin-bottom: 4px; line-height: 1.2; }
    .card-sub { font-size: 0.82rem; color: var(--mid); margin-bottom: 28px; font-weight: 300; }
    .rule-divider { display: flex; align-items: center; gap: 10px; margin-bottom: 24px; }
    .rule-divider span { flex: 1; height: 1px; background: var(--faint); }
    .rule-divider em { font-family: 'IBM Plex Mono', monospace; font-size: 0.6rem; color: #aaa; font-style: normal; letter-spacing: 0.1em; white-space: nowrap; }
    .dashboard-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
    .editor-group { margin-bottom: 8px; }
    .group-tag { display: inline-flex; align-items: center; gap: 8px; font-family: 'IBM Plex Mono', monospace; font-size: 0.64rem; font-weight: 600; letter-spacing: 0.12em; text-transform: uppercase; padding: 6px 12px; margin-bottom: 16px; border: 1px solid var(--rule); background: var(--paper); }
    .group-tag-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
    .group-tag-note { font-weight: 400; color: #aaa; letter-spacing: 0.06em; }
    .group-tag--market { color: var(--ink); border-color: var(--accent); }
    .group-tag--market .group-tag-dot { background: var(--accent); }
    .group-tag--rest { color: var(--mid); }
    .group-tag--rest .group-tag-dot { background: var(--mid); }
    /* ===== Editor description callout — your custom copy goes in these boxes ===== */
    .editor-note { position: relative; margin-top: 16px; padding: 12px 14px; background: #fffdf7; border: 1px solid var(--rule); box-shadow: 2px 2px 0 var(--faint); font-family: 'Source Sans 3', sans-serif; font-size: 0.72rem; line-height: 1.5; color: var(--mid); text-align: left; }
    .editor-note::before { content: ''; position: absolute; top: -7px; left: 22px; width: 12px; height: 12px; background: #fffdf7; border-left: 1px solid var(--rule); border-top: 1px solid var(--rule); transform: rotate(45deg); }
    .editor-note-arrow { display: inline-block; color: var(--accent); font-weight: 700; margin-right: 6px; transform: translateY(1px); }
    .editor-note:empty { display: none; }
    /* Sentiment accents — color shifts with how the editor is described */
    .editor-note--love { border-left: 3px solid #1a7a3c; }            /* top picks */
    .editor-note--love .editor-note-arrow { color: #1a7a3c; }
    .editor-note--good { border-left: 3px solid #1f5fa8; }            /* solid / dependable */
    .editor-note--good .editor-note-arrow { color: #1f5fa8; }
    .editor-note--meh  { border-left: 3px solid #c77d11; }            /* backup / mediocre */
    .editor-note--meh .editor-note-arrow { color: #c77d11; }
    .editor-note--dead { border-left: 3px solid #8a8175; opacity: 0.9; } /* RIP */
    .editor-note--dead .editor-note-arrow { color: #8a8175; }
    /* Claude's two cents */
    .editor-note-claude { display: block; margin-top: 8px; padding-top: 8px; border-top: 1px dashed #d8d2c5; font-style: italic; font-size: 0.68rem; color: #7a7264; }
    .dash-btn { display: block; text-decoration: none; padding: 24px 20px; background: var(--paper); border: 1px solid #c8c2b5; color: var(--ink); text-align: center; transition: all 0.2s; box-shadow: 3px 3px 0 var(--faint); }
    .dash-btn:hover { background: #fff; border-color: var(--ink); box-shadow: 4px 4px 0 var(--ink); transform: translate(-1px, -1px); }
    .dash-btn:active { transform: translate(2px, 2px); box-shadow: 1px 1px 0 var(--ink); }
    .dash-btn-icon { font-size: 2.2rem; margin-bottom: 12px; display: block; }
    .dash-btn-photo-wrap { width: 100%; height: 260px; background: #e0dbd0; margin-bottom: 16px; border: 1px solid #c8c2b5; overflow: hidden; border-radius: 4px; }
    .dash-btn-photo { width: 100%; height: 100%; object-fit: cover; object-position: top; opacity: 0.9; transition: opacity 0.2s; }
    .dash-btn:hover .dash-btn-photo { opacity: 1; }
    .dash-btn-title { font-family: 'IBM Plex Mono', monospace; font-size: 0.8rem; font-weight: 600; letter-spacing: 0.05em; text-transform: uppercase; margin-bottom: 8px; color: var(--ink); }
    .dash-btn-desc { font-size: 0.72rem; color: var(--mid); line-height: 1.4; font-family: 'Source Sans 3', sans-serif; }
    .footer-note { font-family: 'IBM Plex Mono', monospace; font-size: 0.58rem; color: #aaa; text-align: center; margin-top: 28px; letter-spacing: 0.08em; }
  </style>
</head>
<body>
  <div class="page-wrap">
    <div class="masthead">
      <img src="{{ logo_url }}" alt="Newsband" class="masthead-logo" />
      <div class="masthead-tagline">Editorial Intelligence Platform</div>
    </div>
    <div class="dateline">
      <span>SECURE ACCESS PORTAL</span>
      <a href="{{ url_for('login_bp.logout') }}">LOGOUT ⍈</a>
    </div>
    <div class="card">
      <div class="card-headline">Dashboard</div>
      <div class="card-sub">Select a tool to proceed.</div>
      <div class="rule-divider"><span></span><em>NEWSLETTER EDITORS</em><span></span></div>

      <div class="editor-group">
        <div class="group-tag group-tag--market">
          <span class="group-tag-dot"></span>Mon–Fri <span class="group-tag-note">· All Market Days</span>
        </div>
        <div class="dashboard-grid">
          <a href="{{ url_for('day15_editor.editor') }}" class="dash-btn">
            <div class="dash-btn-photo-wrap">
              <img src="/static_files/Day15.png" class="dash-btn-photo" alt="Day15 Editor" />
            </div>
            <div class="dash-btn-title">Day 15 Editor</div>
            <!-- DESCRIPTION ▸ Day 15 Editor -->
            <div class="editor-note editor-note--love"><span class="editor-note-arrow">➤</span>My #1 pick — great aesthetics. Use this if it wasn't used recently.<span class="editor-note-claude">🤖 Claude: {{ q.day15 }}</span></div>
          </a>
          <a href="{{ url_for('day12_2_editor.editor') }}" class="dash-btn">
            <div class="dash-btn-photo-wrap">
              <img src="/static_files/Day12.png" class="dash-btn-photo" alt="Day12(2) Editor" />
            </div>
            <div class="dash-btn-title">Day 12(2) Editor</div>
            <!-- DESCRIPTION ▸ Day 12(2) Editor -->
            <div class="editor-note editor-note--good"><span class="editor-note-arrow">➤</span>My #3 pick — use this in rotation.<span class="editor-note-claude">🤖 Claude: {{ q.day12_2 }}</span></div>
          </a>
          <a href="{{ url_for('day9_2_editor.editor') }}" class="dash-btn">
            <div class="dash-btn-photo-wrap">
              <img src="/static_files/Day9.png" class="dash-btn-photo" alt="Day9(2) Editor" />
            </div>
            <div class="dash-btn-title">Day 9(2) Editor</div>
            <!-- DESCRIPTION ▸ Day 9(2) Editor -->
            <div class="editor-note editor-note--love"><span class="editor-note-arrow">➤</span>My #2 pick — great design. The downside is the limited customization options and the square photos.<span class="editor-note-claude">🤖 Claude: {{ q.day9_2 }}</span></div>
          </a>
          <a href="{{ url_for('day17_editor.editor') }}" class="dash-btn">
            <div class="dash-btn-photo-wrap">
              <img src="/static_files/Day17.png" class="dash-btn-photo" alt="Day17 Editor" />
            </div>
            <div class="dash-btn-title">Day 17 Editor</div>
            <!-- DESCRIPTION ▸ Day 17 Editor -->
            <div class="editor-note editor-note--meh"><span class="editor-note-arrow">➤</span>My last pick — meh design, not really the best.<span class="editor-note-claude">🤖 Claude: {{ q.day17 }}</span></div>
          </a>
        </div>
      </div>

      <div class="editor-group" style="margin-top: 28px;">
        <div class="group-tag group-tag--rest">
          <span class="group-tag-dot"></span>Saturdays <span class="group-tag-note">&amp; Non-Market Days</span>
        </div>
        <div class="dashboard-grid">
          <a href="{{ url_for('day11_editor.editor') }}" class="dash-btn">
            <div class="dash-btn-photo-wrap">
              <img src="/static_files/Day11.png" class="dash-btn-photo" alt="Day11 Editor" />
            </div>
            <div class="dash-btn-title">Day 11 Editor</div>
            <!-- DESCRIPTION ▸ Day 11 Editor -->
            <div class="editor-note editor-note--dead"><span class="editor-note-arrow">➤</span>Dead design. I don't know why I haven't removed it yet. I'm sorry…<span class="editor-note-claude">🤖 Claude: {{ q.day11 }}</span></div>
          </a>
          <a href="{{ url_for('template1_editor.editor') }}" class="dash-btn">
            <div class="dash-btn-photo-wrap">
              <img src="/static_files/template1.png" class="dash-btn-photo" alt="Template1 Editor" />
            </div>
            <div class="dash-btn-title">Template 1 Editor</div>
            <!-- DESCRIPTION ▸ Template 1 Editor -->
            <div class="editor-note editor-note--good"><span class="editor-note-arrow">➤</span>We could use this one again in a while — OG template right here.<span class="editor-note-claude">🤖 Claude: {{ q.template1 }}</span></div>
          </a>
          <a href="{{ url_for('day8_v2_editor.editor') }}" class="dash-btn">
            <div class="dash-btn-photo-wrap">
              <img src="/static_files/Day8.png" class="dash-btn-photo" alt="Day8 Editor" />
            </div>
            <div class="dash-btn-title">Day8 Editor</div>
            <!-- DESCRIPTION ▸ Day8 Editor -->
            <div class="editor-note editor-note--good"><span class="editor-note-arrow">➤</span>Another OG template right here. Good, but it can only carry 4 news items, so if the 5th story is weak we can use this.<span class="editor-note-claude">🤖 Claude: {{ q.day8 }}</span></div>
          </a>
          <a href="{{ url_for('day9_editor.editor') }}" class="dash-btn">
            <div class="dash-btn-photo-wrap">
              <img src="/static_files/Day9.png" class="dash-btn-photo" alt="Day9 Editor" />
            </div>
            <div class="dash-btn-title">Day 9 Editor</div>
            <!-- DESCRIPTION ▸ Day 9 Editor -->
            <div class="editor-note editor-note--love"><span class="editor-note-arrow">➤</span>Great pick. The only downside is the square photo — might need to pick or change the pictures here.<span class="editor-note-claude">🤖 Claude: {{ q.day9 }}</span></div>
          </a>
          <a href="{{ url_for('day12_editor.editor') }}" class="dash-btn">
            <div class="dash-btn-photo-wrap">
              <img src="/static_files/Day12.png" class="dash-btn-photo" alt="Day12 Editor" />
            </div>
            <div class="dash-btn-title">Day 12 Editor</div>
            <!-- DESCRIPTION ▸ Day 12 Editor -->
            <div class="editor-note editor-note--meh"><span class="editor-note-arrow">➤</span>My #4 pick — use this if the others are taken.<span class="editor-note-claude">🤖 Claude: {{ q.day12 }}</span></div>
          </a>
        </div>
      </div>

      <div class="rule-divider" style="margin-top: 36px;"><span></span><em>UTILITY TOOLS</em><span></span></div>
      <div class="dashboard-grid">
        <a href="{{ url_for('codeview_bp.converter') }}" class="dash-btn" style="display: flex; flex-direction: column; justify-content: center; align-items: center;">
          <span class="dash-btn-icon">💻</span>
          <div class="dash-btn-title">Code Viewer</div>
          <!-- DESCRIPTION ▸ Code Viewer -->
          <div class="editor-note editor-note--good" style="text-align: left; align-self: stretch;"><span class="editor-note-arrow">➤</span>Come here — this is the place to come to after you've clicked Export HTML. It'll give you the raw code you need.<span class="editor-note-claude">🤖 Claude: {{ q.code_viewer }}</span></div>
        </a>
        <a href="{{ url_for('extractor_bp.index') }}" target="_blank" class="dash-btn" style="display: flex; flex-direction: column; justify-content: center; align-items: center;">
          <span class="dash-btn-icon">📰</span>
          <div class="dash-btn-title">News Extractor Analyzer</div>
          <!-- DESCRIPTION ▸ News Extractor Analyzer -->
          <div class="editor-note editor-note--dead" style="text-align: left; align-self: stretch;"><span class="editor-note-arrow">➤</span>Dead weight — don't press this. Not useful unless you're fond of doing things the manual way.<span class="editor-note-claude">🤖 Claude: {{ q.news_extractor }}</span></div>
        </a>
        <a href="{{ url_for('batch_extractor_bp.index') }}" target="_blank" class="dash-btn" style="display: flex; flex-direction: column; justify-content: center; align-items: center;">
          <span class="dash-btn-icon">⚡</span>
          <div class="dash-btn-title">Batch Extractor</div>
          <!-- DESCRIPTION ▸ Batch Extractor -->
          <div class="editor-note editor-note--love" style="text-align: left; align-self: stretch;"><span class="editor-note-arrow">➤</span>Extracts and processes multiple news articles at once. This is the place to come when you're starting to make the newsletters — paste all five links, send to template, and this guy's job is done.<span class="editor-note-claude">🤖 Claude: {{ q.batch_extractor }}</span></div>
        </a>
        <a href="{{ url_for('upload_image_bp.index') }}" target="_blank" class="dash-btn" style="display: flex; flex-direction: column; justify-content: center; align-items: center;">
          <span class="dash-btn-icon">🖼️</span>
          <div class="dash-btn-title">Image Uploader</div>
          <!-- DESCRIPTION ▸ Image Uploader -->
          <div class="editor-note editor-note--love" style="text-align: left; align-self: stretch;"><span class="editor-note-arrow">➤</span>This is the superior image uploader — fast and reliable. One thing to keep in mind: it can't process big files, so compress them and give it to him, or change the photo size.<span class="editor-note-claude">🤖 Claude: {{ q.image_uploader }}</span></div>
        </a>
        <a href="{{ url_for('git_pusher_bp.index') }}" target="_blank" class="dash-btn" style="display: flex; flex-direction: column; justify-content: center; align-items: center;">
          <span class="dash-btn-icon">🐙</span>
          <div class="dash-btn-title">Git Image Pusher</div>
          <!-- DESCRIPTION ▸ Git Image Pusher -->
          <div class="editor-note editor-note--meh" style="text-align: left; align-self: stretch;"><span class="editor-note-arrow">➤</span>The inferior image uploader. Slow and inconsistent — might work, might not. High chances of not working.<span class="editor-note-claude">🤖 Claude: {{ q.git_pusher }}</span></div>
        </a>
        <a href="{{ url_for('mailchimp_bp.index') }}" class="dash-btn" style="display: flex; flex-direction: column; justify-content: center; align-items: center;">
          <span class="dash-btn-icon">📬</span>
          <div class="dash-btn-title">Campaign Analytics</div>
          <!-- DESCRIPTION ▸ Campaign Analytics -->
          <div class="editor-note editor-note--love" style="text-align: left; align-self: stretch;"><span class="editor-note-arrow">➤</span>Provides detailed analytics for your email campaigns, including open rates, click-through rates, and conversion metrics. Not for the ones making the newsletter, though.<span class="editor-note-claude">🤖 Claude: {{ q.campaign_analytics }}</span></div>
        </a>
        <a href="{{ url_for('social_pipeline_bp.dashboard') }}" class="dash-btn" style="display: flex; flex-direction: column; justify-content: center; align-items: center;">
          <span class="dash-btn-icon">🚀</span>
          <div class="dash-btn-title">Social Pipeline</div>
          <!-- DESCRIPTION ▸ Social Pipeline -->
          <div class="editor-note editor-note--meh" style="text-align: left; align-self: stretch;"><span class="editor-note-arrow">➤</span>Nothing to see here.<span class="editor-note-claude">🤖 Claude: {{ q.social_pipeline }}</span></div>
        </a>
      </div>
    </div>
    <div class="footer-note">NEWSBAND JOURNALISM PLATFORM &nbsp;·&nbsp; CONFIDENTIAL</div>
  </div>
</body>
</html>
"""


# ── Claude's daily-rotating two cents ──────────────────────────────────────────
# 6 quotes per card, one for each weekday Mon→Sat. The dashboard route picks the
# slot matching today's weekday so the line stays fresh. Index: Mon=0 … Sat=5
# (Sunday falls back to Saturday's). Edit/add freely — just keep 6 per list.
CLAUDE_QUOTES = {
    # ===== Newsletter Editors · Mon–Fri (All Market Days) =====
    'day15': [
        "The valedictorian. Peaked in high school and somehow keeps peaking. I'd trust it with my life and my breakfast order.",
        "The one you bring home to meet the subscribers. Reliable, handsome, never embarrasses you at dinner.",
        "Five stars, would deploy again. Has never once made me open the inspector and sigh.",
        "If templates had a yearbook, this one's 'Most Likely to Succeed' — and it knows it.",
        "The MVP. Carries the whole newsroom and still has the decency to make it look effortless.",
        "Teacher's pet, and honestly? Earned it. Sits up front, raises its hand, gets an A.",
    ],
    'day12_2': [
        "The reliable middle child. Never the favorite, never the problem. Shows up, does the job, asks for nothing.",
        "Old faithful. Not flashy, but it's never once left you stranded at 6 a.m.",
        "The Toyota Corolla of templates. Boring? Maybe. Breaking down? Never.",
        "Quietly competent — the coworker who actually reads the emails and meets the deadline.",
        "No drama, no surprises, no notes. Sometimes that's the whole compliment.",
        "The bench player every coach secretly loves. Always warmed up, never complains.",
    ],
    'day9_2': [
        "Gorgeous, but a control freak about it. Square photos and a short leash — the supermodel who only does one pose.",
        "Stunning, high-maintenance, worth it. The friend who looks incredible but won't let you pick the restaurant.",
        "Looks amazing, argues about everything. Beauty with terms and conditions attached.",
        "Editorial royalty — just don't ask it to crop anything other than a perfect square. It will not.",
        "All killer visuals, zero flexibility. A diva, but the kind that actually delivers the show.",
        "Photogenic to a fault. Insists on the square format like it's a personal brand. Which, honestly, it is.",
    ],
    'day17': [
        "It's trying its best, bless it. Not the one you call first, but it'll answer when everyone else is busy.",
        "Participation-trophy energy. Showed up, technically functions, we clap politely.",
        "The 'fine, I guess' of templates. Nobody's first choice, nobody's enemy.",
        "Like elevator music — it exists, it's inoffensive, you forget it the moment it's gone.",
        "Off the bench in garbage time. Won't lose the game, won't win it either.",
        "A solid C+. Could've studied harder, chose not to, still passed.",
    ],
    # ===== Newsletter Editors · Saturdays & Non-Market Days =====
    'day11': [
        "Pour one out. It's not dead, it's resting. (It's dead.) Press F to pay respects, then maybe finally hit delete.",
        "Still here out of pure guilt. The houseplant you stopped watering but can't throw away.",
        "Functionally a ghost. Haunts the dashboard, scares no one, helps less.",
        "On life support held up entirely by 'I'll deal with it later.' You will not.",
        "The gym membership of templates — paid for, never used, too awkward to cancel.",
        "Schrödinger's editor: simultaneously kept and abandoned until someone finally opens the trash.",
    ],
    'template1': [
        "The OG. Vintage, classic, slightly dusty — the vinyl record of templates. Still slaps on the right day.",
        "Old school and proud. Black-and-white photo on the mantel, but the smile's still got it.",
        "The founding father. Built different, literally — everything else descends from this one.",
        "Retro charm. Like a typewriter: nobody needs it, everybody respects it.",
        "Grandpa template. Tells the same stories, but they're good stories, so you listen.",
        "A classic for a reason. Dust it off the right week and it still turns heads.",
    ],
    'day8': [
        "Carries exactly 4 stories and not one more — bouncer energy. Strict capacity, but a clean venue.",
        "Four items. Hard stop. The velvet rope of newsletters — list's full, buddy.",
        "Minimalist by force, not choice. 'We're at capacity' is its entire personality.",
        "Knows its limits and enforces them. Refreshingly honest for a template.",
        "Small venue, great acoustics. Only fits four acts, but every one gets the spotlight.",
        "The 'four is plenty' philosopher. Quality over quantity, and it will die on that hill.",
    ],
    'day9': [
        "Great taste, just picky about its headshots. Square photos only, like it's perpetually applying for a passport.",
        "Excellent, with one quirk: it treats every photo like a mugshot. Look straight ahead.",
        "Top-tier work, square-shaped opinions. Crop accordingly and it'll make you proud.",
        "A keeper that just really, really loves a 1:1 ratio. We don't ask why anymore.",
        "Strong choice — comes with homework. Pick the right pics and it shines.",
        "Brilliant but bureaucratic about formats. Fill out the square in triplicate, please.",
    ],
    'day12': [
        "The understudy. Steps in when the stars are taken and quietly nails it anyway. Underrated, honestly.",
        "The backup quarterback. You hope you don't need it, you're glad it's there.",
        "Fourth in line, first to never complain about it. Quietly dependable.",
        "The spare tire. Not glamorous, but you'll be very grateful at the worst possible moment.",
        "Plan D, executed like Plan A. Low billing, solid performance.",
        "The 'break glass in case of emergency' option. Dusty, but it works every time.",
    ],
    # ===== Utility Tools =====
    'code_viewer': [
        "Ctrl+C's emotional support animal. Doesn't ask questions, doesn't judge your markup — just hands the code back warm.",
        "The copy-paste concierge. You arrive with chaos, you leave with clipboard.",
        "A vending machine for raw HTML. Insert click, receive code, no small talk.",
        "The quiet final step nobody thanks. Holds the door, hands you the code, says nothing.",
        "Read-only and at peace with it. Shows you everything, touches nothing.",
        "The getaway driver of the workflow. Pulls up, you grab the code, you're gone.",
    ],
    'news_extractor': [
        "The bloodhound of the newsroom. Sniffs one clean headline out of a 4,000-word swamp of cookie banners and ad slop. Bless it.",
        "Wildly capable, professionally unemployed. Batch Extractor took its job and its lunch.",
        "The manual transmission in an automatic world. Works great, nobody wants to drive it.",
        "Single-article energy in a paste-five-links era. Skilled, obsolete, a little tragic.",
        "Does one article beautifully and very slowly. The artisanal sourdough of extractors.",
        "Press it only if you enjoy the long way round. It does not judge — it just sighs.",
    ],
    'batch_extractor': [
        "Does the work of seven interns and never once asks for coffee. Parallel, caffeinated, and a little terrifying.",
        "Paste five links, walk away, come back to a finished day. Borderline witchcraft.",
        "The assembly line that made the artisans cry. Fast, ruthless, brilliant.",
        "Eats five articles for breakfast and asks if you've got more. Unbothered. Efficient.",
        "The opening move of every newsletter. Press it and 80% of your morning evaporates — in a good way.",
        "Multitasking as a personality. Does everything at once and somehow never drops a plate.",
    ],
    'image_uploader': [
        "Drag, drop, done. The vending machine of URLs — feed it a picture, a link falls out. Deeply, suspiciously satisfying.",
        "Fast, reliable, allergic to big files. Compress first and it'll love you forever.",
        "The express lane of uploads. Just don't show up with a 40MB carry-on.",
        "Turns pictures into links faster than you can say 'optimize.' A simple joy.",
        "Superior cousin, knows it. Quick and a little smug, but it earns the attitude.",
        "Smooth operator with one rule: keep it light. Respect the file limit and it never misses.",
    ],
    'git_pusher': [
        "Image Uploader's overachieving cousin who insists on doing it 'the proper way' with version control. Nobody asked, but… okay.",
        "The scenic route to a URL. Might arrive, might not, definitely takes its time.",
        "Coin-flip reliability with extra steps. Heads it uploads, tails you try again.",
        "Technically more 'correct,' practically more 'why isn't this working.' Choose your fighter.",
        "The slow lane with commit messages. Does it matter? It thinks so. Loudly.",
        "High effort, medium results. The group-project member who insists on a 'proper process.'",
    ],
    'campaign_analytics': [
        "Finally, numbers that tell the truth. Opens, clicks, and the cold hard tally of everyone who ghosted you. Spicy.",
        "The receipts. Who opened, who clicked, who pretended your email never arrived — all here.",
        "A mirror that doesn't flatter. Beautiful campaign, mediocre open rate? It'll tell you. Bluntly.",
        "Scoreboard for the newsroom. The metrics don't lie, even when you'd prefer they did.",
        "The morning-after stats. Thrilling if you did well, humbling if you didn't.",
        "Turns vibes into hard numbers. Closure for the data-hungry, anxiety for everyone else.",
    ],
    'social_pipeline': [
        "The breaker box. You only open it when something's already on fire, and you always look a little afraid while doing it.",
        "The 'do not touch unless broken' panel. Mostly you just hope you never have to.",
        "Backstage machinery. Runs itself until the one day it dramatically doesn't.",
        "The reset button behind glass. Calm, ominous, best left alone.",
        "Plumbing. You don't think about it until something's leaking — then it's all you think about.",
        "The quiet engine room. No tourists, no view, just levers you pray you won't pull.",
    ],
}


@dashboard_bp.route('/dashboard')
@require_login
def dashboard():
    """Dashboard page — routes to Editor or Converter."""
    # Mon=0 … Sat=5; Sunday (6) falls back to Saturday's quote.
    idx = min(datetime.now().weekday(), 5)
    todays_quotes = {key: quotes[idx] for key, quotes in CLAUDE_QUOTES.items()}
    return render_template_string(
        DASHBOARD_HTML,
        logo_url=config.LOGO_URL,
        q=todays_quotes,
    )

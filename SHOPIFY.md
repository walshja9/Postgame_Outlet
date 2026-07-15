# Putting the ratings on postgameoutlet.com (Shopify)

The site is one self-contained `index.html` (inline CSS + JS, no external files).
Shopify's page editor **strips `<script>` and `<style>` tags**, so you can't just
paste the HTML into a page. The reliable way to embed it is a two-step: host the
file statically, then drop an `<iframe>` into a Shopify page.

## Step 1 — Host the file (pick one)

The file is static, so any of these work and all have a free tier:

- **GitHub Pages** — create a repo, add `index.html`, enable Pages. URL looks like
  `https://<you>.github.io/nfl-power-ratings/`.
- **Netlify drop** — go to app.netlify.com/drop and drag the folder in. Instant URL.
- **Cloudflare Pages / S3 static site** — same idea if you already use one.

Whichever you pick, the goal is a public HTTPS URL that serves `index.html`.
Re-uploading the regenerated file (after you edit ratings/write-ups) is the only
"deploy" step. Netlify drop and GitHub both let you re-drag / re-commit.

## Step 2 — Embed it in a Shopify page

1. Shopify admin → **Online Store → Pages → Add page**. Title it e.g. "Power Ratings".
2. In the content box, click the **`<>` (Show HTML)** button.
3. Paste this, swapping in your hosted URL (both places):

   ```html
   <iframe id="npr-frame"
     src="https://YOUR-HOSTED-URL/index.html"
     style="width:100%;height:1600px;border:0;display:block"
     loading="lazy"
     title="NFL Power Ratings"></iframe>
   <script>
   (function () {
     var f = document.getElementById('npr-frame');
     var origin = new URL(f.src).origin;          // only trust the ratings site
     // Parent -> child: report which vertical slice of the iframe is on screen,
     // so the team drawer pins to the visible area (not the whole tall frame).
     function sendViewport() {
       var r = f.getBoundingClientRect();
       var top = Math.max(0, -r.top);                          // scrolled-past px
       var vh = window.innerHeight || document.documentElement.clientHeight;
       var height = Math.max(0, Math.min(r.bottom, vh) - Math.max(r.top, 0));
       f.contentWindow.postMessage(
         { type: 'npr:viewport', top: top, height: height }, origin);
     }
     window.addEventListener('message', function (e) {
       if (e.origin !== origin || !e.data) return;
       if (e.data.type === 'npr:height') f.style.height = e.data.height + 'px';
       if (e.data.type === 'npr:ready') sendViewport();
     });
     window.addEventListener('scroll', sendViewport, { passive: true });
     window.addEventListener('resize', sendViewport);
   })();
   </script>
   ```

4. Save. The page will live at `postgameoutlet.com/pages/power-ratings`.
5. Add it to your store nav: **Online Store → Navigation → Main menu → Add menu item**.

### How the script fixes the two iframe gotchas
Both are handled automatically — you don't tune anything:
- **Auto-height.** The page measures its own content and posts its height; the
  parent resizes the iframe to match. No inner scrollbar, no clipping, no guessing
  a `min-height`. The `height:1600px` above is only a first-paint placeholder
  before the script runs. If you ever strip the `<script>`, the page still works —
  it just falls back to that fixed height.
- **Drawer pinning.** Because the team drawer is `position:fixed`, inside an iframe
  it would otherwise anchor to the (very tall) frame instead of the visible window.
  The parent posts the on-screen slice on scroll/resize; the page pins the drawer
  and dim-overlay to exactly that slice, so it stays put and centered as you scroll.
- Both the `<iframe>` and `<script>` tags survive Shopify's page-HTML editor when
  entered via the `<>` view. (The site's *own* inline `<script>` is what Shopify
  would strip — which is why we host the file and embed it, rather than pasting its
  HTML directly.)

### If you skip the `<script>`
The iframe still renders and every tab works. You'd just: (a) set a generous fixed
`height` (e.g. `2600px`) so nothing clips, and (b) accept that the drawer pins to
the iframe rather than the viewport. The script is strongly recommended, but the
page degrades gracefully without it.

## Alternative — native Shopify (more work, no iframe)

If you'd rather not host externally, the HTML can be split into a **custom Liquid
section**: put the markup in a `section` file, move the CSS into the theme's
stylesheet, and load the JS via the theme's assets. This is the "proper" Shopify
way but requires theme-file access and re-splitting on every change. The iframe
route above keeps `generate_site.py` as the single source of truth, so start there.

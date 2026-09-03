(() => {
  'use strict';

  document.addEventListener('click', (event) => {
    if (!(event.target instanceof Element)) return;
    const link = event.target.closest('#MainContent a[href*="/products/"]');
    const { postgameContentType: content_type, postgameContentId: content_identifier } = document.body.dataset;
    if (!link || !content_type || !content_identifier || !window.Shopify?.analytics?.publish) return;

    const match = new URL(link.href, location.origin).pathname.match(/^\/products\/([^/]+)\/?$/);
    if (!match) return;
    try {
      window.Shopify.analytics.publish('postgame_content_product_click', {
        content_type,
        content_identifier,
        product_handle: decodeURIComponent(match[1]),
      })?.catch?.(() => {});
    } catch (_) {
      // ponytail: analytics must never block navigation.
    }
  });

  document.querySelectorAll('[data-postgame-ratings-frame]').forEach((frame) => {
    const url = new URL(frame.src);
    if (url.protocol !== 'https:') return;
    const origin = url.origin;

    const sendViewport = () => {
      const rect = frame.getBoundingClientRect();
      const viewport = window.innerHeight || document.documentElement.clientHeight;
      frame.contentWindow?.postMessage({
        type: 'npr:viewport',
        top: Math.max(0, -rect.top),
        height: Math.max(0, Math.min(rect.bottom, viewport) - Math.max(rect.top, 0)),
      }, origin);
    };

    addEventListener('message', (event) => {
      if (event.source !== frame.contentWindow || event.origin !== origin || !event.data) return;
      if (event.data.type === 'npr:ready') sendViewport();
      if (event.data.type === 'npr:height') {
        const height = Number(event.data.height);
        if (Number.isFinite(height) && height >= 400 && height <= 30000) {
          frame.style.height = `${Math.ceil(height)}px`;
        }
      }
    });
    addEventListener('scroll', sendViewport, { passive: true });
    addEventListener('resize', sendViewport);
  });
})();

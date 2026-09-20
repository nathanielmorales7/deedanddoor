document.addEventListener('DOMContentLoaded', function () {
  var toggle = document.querySelector('.navtoggle');
  var menu = document.querySelector('.navmobile');
  var links = document.querySelector('.navlinks');
  var cta = document.querySelector('.navcta');
  if (!toggle || !menu || !links) return;

  menu.innerHTML = links.innerHTML + (cta ? cta.outerHTML : '');

  toggle.addEventListener('click', function () {
    var isOpen = menu.classList.toggle('open');
    toggle.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
  });

  menu.addEventListener('click', function (e) {
    var trigger = e.target.closest('.navdrop-trigger');
    if (trigger) {
      trigger.parentElement.classList.toggle('mobile-open');
      return;
    }
    if (e.target.tagName === 'A') {
      menu.classList.remove('open');
      toggle.setAttribute('aria-expanded', 'false');
    }
  });
});

document.addEventListener('DOMContentLoaded', function () {
  document.querySelectorAll('.navlinks .navdrop').forEach(function (drop) {
    var closeTimer = null;

    function openDrop() {
      clearTimeout(closeTimer);
      drop.classList.add('hover-open');
    }

    function scheduleClose() {
      clearTimeout(closeTimer);
      closeTimer = setTimeout(function () {
        drop.classList.remove('hover-open');
      }, 400);
    }

    drop.addEventListener('mouseenter', openDrop);
    drop.addEventListener('mouseleave', scheduleClose);
    drop.addEventListener('focusin', openDrop);
    drop.addEventListener('focusout', scheduleClose);
  });
});

// Lead-capture popup modal: any element with class "lead-capture-btn" opens it
document.addEventListener('DOMContentLoaded', function () {
  var overlay = document.getElementById('lead-modal-overlay');
  if (!overlay) return;

  document.querySelectorAll('.lead-capture-btn').forEach(function (btn) {
    btn.addEventListener('click', function (e) {
      e.preventDefault();
      overlay.classList.add('open');
    });
  });

  var closeBtn = overlay.querySelector('.lead-modal-close');
  if (closeBtn) {
    closeBtn.addEventListener('click', function () {
      overlay.classList.remove('open');
    });
  }

  overlay.addEventListener('click', function (e) {
    if (e.target === overlay) overlay.classList.remove('open');
  });

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') overlay.classList.remove('open');
  });
});
   // GoHighLevel External Tracking (page views + form submissions)
   document.addEventListener('DOMContentLoaded', function () {
     var s = document.createElement('script');
     s.src = 'https://link.msgsndr.com/js/external-tracking.js';
     s.setAttribute('data-tracking-id', 'tk_79a8cf7ea2f64eef89de8f5efaa0fafa');
     document.body.appendChild(s);
   });

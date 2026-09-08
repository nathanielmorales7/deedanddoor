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

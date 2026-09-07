document.addEventListener('DOMContentLoaded', function () {
  document.querySelectorAll('.guide-item').forEach(function (item) {
    var q = item.querySelector('.guide-q');
    if (!q) return;
    q.addEventListener('click', function () {
      item.classList.toggle('open');
    });
  });
});

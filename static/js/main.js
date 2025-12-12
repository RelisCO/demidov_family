// main.js - улучшение пользовательского интерфейса

document.addEventListener('DOMContentLoaded', function () {
    // Закрытие алертов при клике и автоматически
    const alerts = document.querySelectorAll('.alert');
    alerts.forEach((alert) => {
        const closeBtn = alert.querySelector('.btn-close'); // Исправлен селектор
        if (closeBtn) {
            closeBtn.addEventListener('click', () => {
                alert.style.display = 'none';
            });
        }

        // Автоматическое скрытие (кроме ошибок)
        if (!alert.classList.contains('alert-danger')) {
            setTimeout(() => {
                alert.style.opacity = '0';
                alert.style.transition = 'opacity 0.5s';
                setTimeout(() => (alert.style.display = 'none'), 500);
            }, 5000);
        }
    });

    // Подтверждение выхода
    const logoutLinks = document.querySelectorAll('.logout-link');
    logoutLinks.forEach((link) => {
        link.addEventListener('click', function (e) {
            if (!confirm('Вы уверены, что хотите выйти?')) {
                e.preventDefault();
            }
        });
    });

    // Анимация баланса
    const balanceBadges = document.querySelectorAll('.balance-badge');
    balanceBadges.forEach((badge) => {
        badge.addEventListener('mouseenter', function () {
            this.style.transform = 'scale(1.1)';
            this.style.transition = 'transform 0.3s';
        });

        badge.addEventListener('mouseleave', function () {
            this.style.transform = 'scale(1)';
        });
    });
});

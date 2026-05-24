// ============================================
// SISTEMA DE DARK/LIGHT MODE
// ============================================

(function () {
    'use strict';

    const THEME_KEY = 'app-theme';
    const DARK_THEME = 'dark';
    const LIGHT_THEME = 'light';

    const THEME_VARS = {
        dark: {
            '--bg-primary': '#07111f',
            '--bg-secondary': '#0d1b31',
            '--bg-card': '#0f1f3a',
            '--bg-card-hover': '#132746',
            '--bg-surface': 'rgba(255, 255, 255, 0.04)',
            '--accent': '#5d8eff',
            '--accent-dark': '#3f6fe0',
            '--accent-light': '#a8c7ff',
            '--success': '#68d39a',
            '--warning': '#f3bb6d',
            '--danger': '#f07279',
            '--text-primary': '#f4f8ff',
            '--text-secondary': '#c7d4ee',
            '--text-muted': '#90a3c4',
            '--border': 'rgba(255, 255, 255, 0.12)',
            '--border-light': 'rgba(255, 255, 255, 0.08)',
            '--shadow-card': '0 18px 45px rgba(0, 0, 0, 0.24)',
            '--page-orb-1': 'rgba(93, 142, 255, 0.16)',
            '--page-orb-2': 'rgba(77, 211, 172, 0.08)',
            '--page-orb-3': 'rgba(255, 255, 255, 0.04)'
        },
        light: {
            '--bg-primary': '#f4f7fb',
            '--bg-secondary': '#e8eef7',
            '--bg-card': '#ffffff',
            '--bg-card-hover': '#f7f9fc',
            '--bg-surface': 'rgba(15, 23, 42, 0.03)',
            '--accent': '#4676ff',
            '--accent-dark': '#2f5de0',
            '--accent-light': '#dbe6ff',
            '--success': '#0f9d72',
            '--warning': '#d98f1e',
            '--danger': '#df4b56',
            '--text-primary': '#132033',
            '--text-secondary': '#415066',
            '--text-muted': '#718096',
            '--border': 'rgba(15, 23, 42, 0.10)',
            '--border-light': 'rgba(15, 23, 42, 0.06)',
            '--shadow-card': '0 18px 45px rgba(15, 23, 42, 0.08)',
            '--page-orb-1': 'rgba(70, 118, 255, 0.16)',
            '--page-orb-2': 'rgba(15, 157, 114, 0.07)',
            '--page-orb-3': 'rgba(255, 255, 255, 0.5)'
        }
    };

    function getSystemTheme() {
        if (window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches) {
            return LIGHT_THEME;
        }
        return DARK_THEME;
    }

    function getSavedTheme() {
        const saved = localStorage.getItem(THEME_KEY);
        return saved === LIGHT_THEME || saved === DARK_THEME ? saved : getSystemTheme();
    }

    function applyTheme(theme) {
        const resolvedTheme = theme === LIGHT_THEME ? LIGHT_THEME : DARK_THEME;
        const html = document.documentElement;
        const vars = THEME_VARS[resolvedTheme];

        html.setAttribute('data-theme', resolvedTheme);
        html.style.colorScheme = resolvedTheme;
        Object.entries(vars).forEach(([key, value]) => {
            html.style.setProperty(key, value);
        });

        // Trocar logo dependendo do tema
        const logo = document.getElementById('app-logo');
        if (logo) {
            logo.src = resolvedTheme === LIGHT_THEME ? '/static/logo2.png' : '/static/logo.png';
        }



        localStorage.setItem(THEME_KEY, resolvedTheme);
        updateThemeButton();
    }

    function updateThemeButton() {
        const button = document.querySelector('.theme-toggle-btn');
        if (!button) return;

        const icon = button.querySelector('i');
        const theme = document.documentElement.getAttribute('data-theme') || DARK_THEME;
        const isLight = theme === LIGHT_THEME;

        if (icon) {
            icon.className = isLight ? 'bi bi-moon-stars-fill' : 'bi bi-sun-fill';
        }

        button.setAttribute('aria-label', isLight ? 'Ativar modo escuro' : 'Ativar modo claro');
        button.title = isLight ? 'Modo Escuro' : 'Modo Claro';
    }

    function toggleTheme() {
        const currentTheme = document.documentElement.getAttribute('data-theme') || DARK_THEME;
        applyTheme(currentTheme === LIGHT_THEME ? DARK_THEME : LIGHT_THEME);
    }

    function bindToggleButton() {
        const button = document.querySelector('.theme-toggle-btn');
        if (!button || button.dataset.themeBound === 'true') return;

        button.dataset.themeBound = 'true';
        button.addEventListener('click', toggleTheme);
    }

    function watchSystemTheme() {
        if (!window.matchMedia) return;

        const mediaQuery = window.matchMedia('(prefers-color-scheme: light)');
        const handleChange = (event) => {
            if (!localStorage.getItem(THEME_KEY)) {
                applyTheme(event.matches ? LIGHT_THEME : DARK_THEME);
            }
        };

        if (mediaQuery.addEventListener) {
            mediaQuery.addEventListener('change', handleChange);
        } else if (mediaQuery.addListener) {
            mediaQuery.addListener(handleChange);
        }
    }

    function init() {
        applyTheme(getSavedTheme());
        bindToggleButton();
        watchSystemTheme();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    window.toggleTheme = toggleTheme;
    window.applyTheme = applyTheme;
    window.getSavedTheme = getSavedTheme;
})();

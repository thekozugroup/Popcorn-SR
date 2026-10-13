import {defineTheme} from '@astryxdesign/core/theme';
import {neutralTheme, neutralIconRegistry} from '@astryxdesign/theme-neutral/built';

// Extend the official theme. Compile at build time to keep styles local and CSP strict.
export const popcornTheme = defineTheme({
  name: 'popcorn',
  extends: neutralTheme,
  icons: neutralIconRegistry,
  color: {accent: ['#3b82f6', '#3b82f6'], neutralStyle: 'neutral'},
  typography: {
    scale: {base: 15, ratio: 1.2},
    body: {family: '-apple-system', fallbacks: 'BlinkMacSystemFont, "Segoe UI", sans-serif'},
    heading: {family: '-apple-system', fallbacks: 'BlinkMacSystemFont, "Segoe UI", sans-serif'},
  },
  motion: {fast: 125, medium: 250, ratio: 0.75},
  tokens: {
    '--color-background-body': ['#fafafa', '#09090b'],
    '--color-background-surface': ['#ffffff', '#18181b'],
    '--color-background-card': ['#ffffff', '#18181b'],
    '--color-background-popover': ['#ffffff', '#18181b'],
    '--color-background-muted': ['#f4f4f5', '#27272a'],
    '--color-text-primary': ['#18181b', '#fafafa'],
    '--color-text-secondary': ['#52525b', '#a1a1aa'],
    '--color-text-disabled': ['#71717a', '#a1a1aa'],
    '--color-border': ['#e4e4e7', '#3f3f46'],
    '--color-border-emphasized': ['#a1a1aa', '#71717a'],
    '--color-accent': '#3b82f6',
    '--color-on-accent': '#09090b',
    '--color-text-accent': ['#1d4ed8', '#93c5fd'],
    '--color-icon-accent': ['#1d4ed8', '#93c5fd'],
    '--size-element-sm': '44px',
    '--size-element-md': '44px',
    '--size-element-lg': '48px',
    '--text-heading-1-size': '2rem',
    '--text-heading-1-leading': '1.2',
  },
  components: {
    'collapsible-trigger': {base: {minHeight: '44px'}},
    button: {base: {minHeight: '44px', minWidth: '44px', flexShrink: '0'}},
    'text-input': {base: {minHeight: '44px'}},
    'number-input': {base: {minHeight: '44px', paddingBlock: '0'}},
    selector: {base: {minHeight: '44px'}},
    'side-nav-item': {base: {minHeight: '44px'}},
    'checkbox-input': {base: {minHeight: '44px'}},
  },
});

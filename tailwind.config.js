/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./templates/**/*.html",
    "./static/src/**/*.js", // Or wherever your main JS is, e.g., "./static/js/**/*.js"
    "./node_modules/flowbite/**/*.js"
  ],
  theme: {
    extend: {
      colors: {
        'primary-green': '#0aad4e',
        'accent-color': '#ff914d',
        'success-green': '#2ecc71',
        'danger-red': '#e74c3c',
        'text-dark': '#333333',
      },
    },
  },
  plugins: [
    require('flowbite/plugin')
  ],
}
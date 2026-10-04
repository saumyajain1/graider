'use strict'

SwaggerUIBundle({
  url: '{{ schema_url|escapejs }}',
  dom_id: '#swagger-ui',
  presets: [SwaggerUIBundle.presets.apis],
  layout: 'BaseLayout',
  ...JSON.parse('{{ settings|escapejs }}'),
  requestInterceptor: (request) => {
    const target = new URL(request.url, window.location.href)
    if (target.origin === window.location.origin) {
      request.credentials = 'same-origin'
      if (!['GET', 'HEAD', 'OPTIONS'].includes(request.method?.toUpperCase())) {
        const cookie = document.cookie.split('; ').find((value) => value.startsWith('csrftoken='))
        if (cookie)
          request.headers['X-CSRFToken'] = decodeURIComponent(cookie.slice('csrftoken='.length))
      }
    }
    return request
  },
})

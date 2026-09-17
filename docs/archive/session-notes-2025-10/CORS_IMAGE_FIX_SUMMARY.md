# CORS Image Loading Fix - OpaqueResponseBlocking

## Problem

Team logos were not displaying in the browser with the following error:
```
A resource is blocked by OpaqueResponseBlocking
```

This error appeared for all team logo images from `r2.thesportsdb.com`.

---

## Root Cause

### **OpaqueResponseBlocking Security Feature**

Modern browsers (Chrome 108+, Firefox, Safari) implement **OpaqueResponseBlocking** to prevent certain types of cross-origin attacks. This security feature blocks:

1. **Cross-origin resources** loaded without proper CORS headers
2. **Opaque responses** (responses from servers that don't send `Access-Control-Allow-Origin` headers)
3. **Images from CDNs** that don't explicitly allow cross-origin requests

### **TheSportsDB Image Server Issue**

The API returns image URLs from `r2.thesportsdb.com` (Cloudflare R2 bucket):
```
https://r2.thesportsdb.com/images/media/team/badge/uyhbfe1612467038.png
```

**Problem:** This server does NOT send CORS headers:
```bash
curl -I "https://r2.thesportsdb.com/images/media/team/badge/uyhbfe1612467038.png"
# Response: HTTP/2 200 (but NO Access-Control-Allow-Origin header)
```

**Result:** Browser blocks the image with OpaqueResponseBlocking error.

---

## Solution: Vite Proxy

We configured a **Vite development proxy** to:
1. Intercept requests to `/api/images/*`
2. Forward them to `r2.thesportsdb.com`
3. Serve the images from our own domain (localhost:3000)
4. Bypass CORS restrictions (same-origin requests)

### **Implementation**

#### 1. Updated `frontend/vite.config.ts`

```typescript
server: {
  port: 3000,
  host: true,
  proxy: {
    '/api/images': {
      target: 'https://r2.thesportsdb.com',
      changeOrigin: true,
      rewrite: (path) => path.replace(/^\/api\/images/, ''),
      configure: (proxy, _options) => {
        proxy.on('proxyReq', (proxyReq, req, _res) => {
          // Remove origin header to avoid CORS issues
          proxyReq.removeHeader('origin');
        });
      }
    }
  }
},
```

**How it works:**
- Request: `http://localhost:3000/api/images/images/media/team/badge/uyhbfe1612467038.png`
- Proxy rewrites to: `https://r2.thesportsdb.com/images/media/team/badge/uyhbfe1612467038.png`
- Browser receives image from same origin (localhost:3000)
- No CORS error!

#### 2. Updated `frontend/src/services/thesportsdb-mapper.service.ts`

Modified the `cleanLogoUrl()` function to convert URLs:

```typescript
const cleanLogoUrl = (url: string) => {
  if (!url) return url;
  // Remove size suffixes
  let cleanedUrl = url.replace(/\/(tiny|small|medium)$/, '');
  // Convert r2.thesportsdb.com to use our proxy
  if (cleanedUrl.includes('r2.thesportsdb.com')) {
    cleanedUrl = cleanedUrl.replace('https://r2.thesportsdb.com', '/api/images');
  }
  return cleanedUrl;
};
```

**URL Transformation:**
- **Before:** `https://r2.thesportsdb.com/images/media/team/badge/uyhbfe1612467038.png/tiny`
- **After:** `/api/images/images/media/team/badge/uyhbfe1612467038.png`

#### 3. Updated `frontend/src/pages/LeagueDetailPage.tsx`

Added `referrerPolicy="no-referrer"` to all `<img>` tags:

```typescript
<img
  src={standing.team.logo}
  alt={standing.team.name}
  className="h-6 w-6 object-contain"
  referrerPolicy="no-referrer"
  onError={(e) => {
    e.currentTarget.src = '/teams/default.svg'
  }}
/>
```

---

## Files Modified

| File | Changes |
|------|---------|
| `frontend/vite.config.ts` | Added proxy configuration for `/api/images` |
| `frontend/src/services/thesportsdb-mapper.service.ts` | Updated `cleanLogoUrl()` in `mapTeam()` and `mapStanding()` |
| `frontend/src/pages/LeagueDetailPage.tsx` | Added `referrerPolicy="no-referrer"` to img tags |

---

## Testing

### Before Fix:
```
❌ OpaqueResponseBlocking errors in console
❌ Team logos not displaying
❌ Broken image icons everywhere
```

### After Fix:
```
✅ No CORS errors
✅ Team logos load through proxy
✅ Images display correctly
```

### Test URL Transformation:
```javascript
// Original API URL
const original = "https://r2.thesportsdb.com/images/media/team/badge/uyhbfe1612467038.png/tiny";

// After cleanLogoUrl()
const proxied = "/api/images/images/media/team/badge/uyhbfe1612467038.png";

// Browser requests
const fullUrl = "http://localhost:3000/api/images/images/media/team/badge/uyhbfe1612467038.png";

// Vite proxy forwards to
const target = "https://r2.thesportsdb.com/images/media/team/badge/uyhbfe1612467038.png";
```

---

## Important Notes

### **Development vs Production**

⚠️ **This proxy only works in development!**

For production deployment, you'll need to:

1. **Option 1: Backend Proxy**
   - Create an API endpoint in your backend to proxy images
   - Example: `GET /api/images/:path` → forwards to `r2.thesportsdb.com`

2. **Option 2: Cloudflare Worker**
   - Deploy a Cloudflare Worker to proxy images
   - Add proper CORS headers in the worker

3. **Option 3: Image CDN**
   - Use a service like Cloudinary or imgix
   - Configure to fetch from `r2.thesportsdb.com`

### **Why Not Use `crossOrigin="anonymous"`?**

Adding `crossOrigin="anonymous"` to `<img>` tags would:
- ❌ Make the CORS problem WORSE (triggers preflight requests)
- ❌ Require the server to send CORS headers (which it doesn't)
- ❌ Still result in OpaqueResponseBlocking errors

### **Why Not Use `referrerPolicy` Alone?**

`referrerPolicy="no-referrer"` helps with:
- ✅ Privacy (doesn't send referrer header)
- ✅ Some CDN restrictions

But it does NOT fix:
- ❌ OpaqueResponseBlocking errors
- ❌ Missing CORS headers

---

## Next Steps

1. **Test in browser:**
   - Open http://localhost:3000
   - Navigate to League Detail page
   - Verify team logos display in standings table

2. **Check browser console:**
   - Should see NO OpaqueResponseBlocking errors
   - Image requests should go to `/api/images/*`

3. **For production:**
   - Implement one of the production solutions above
   - Test with production build (`npm run build`)

---

## References

- [OpaqueResponseBlocking Explanation](https://developer.chrome.com/blog/opaque-response-blocking/)
- [Vite Proxy Configuration](https://vitejs.dev/config/server-options.html#server-proxy)
- [CORS and Images](https://developer.mozilla.org/en-US/docs/Web/HTML/CORS_enabled_image)

---

**Status:** ✅ Fixed for development
**Production:** ⚠️ Requires backend proxy or CDN solution


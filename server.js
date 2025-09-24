const http = require('http');
const fs = require('fs');
const path = require('path');

const server = http.createServer((req, res) => {
    // Default to serving soccer-app.html for all requests
    let filePath = path.join(__dirname, 'soccer-app.html');
    
    // Set proper content type
    const ext = path.extname(filePath);
    let contentType = 'text/html';
    
    if (ext === '.css') contentType = 'text/css';
    else if (ext === '.js') contentType = 'application/javascript';
    else if (ext === '.json') contentType = 'application/json';
    else if (ext === '.png') contentType = 'image/png';
    else if (ext === '.jpg') contentType = 'image/jpeg';
    else if (ext === '.svg') contentType = 'image/svg+xml';
    
    // Read and serve the file
    fs.readFile(filePath, (err, data) => {
        if (err) {
            res.writeHead(404, {'Content-Type': 'text/html'});
            res.end('<h1>404 - File Not Found</h1>');
            return;
        }
        
        res.writeHead(200, {
            'Content-Type': contentType,
            'Cache-Control': 'no-cache'
        });
        res.end(data);
    });
});

const PORT = 3000;
server.listen(PORT, () => {
    console.log(`✅ Soccer Predictions App Server running on http://localhost:${PORT}`);
    console.log(`🌐 Open your browser and go to: http://localhost:${PORT}`);
    console.log(`⚽ Your professional soccer predictions website is ready!`);
});

// Handle server errors
server.on('error', (err) => {
    if (err.code === 'EADDRINUSE') {
        console.log(`❌ Port ${PORT} is already in use. Trying port ${PORT + 1}...`);
        server.listen(PORT + 1);
    } else {
        console.error('Server error:', err);
    }
});

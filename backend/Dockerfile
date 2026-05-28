FROM node:24-alpine

WORKDIR /app

# Install production dependencies
COPY package.json package-lock.json tsconfig.json ./
RUN npm ci --omit=dev

# Copy source code
COPY . .

# Build TypeScript
RUN npm run build || true

# Expose port
EXPOSE 8000

# Start the compiled server
CMD ["node", "dist/server.js"]

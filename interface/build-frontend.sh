(
  cd dammian-mask-frontend
  bun run build
)

cp -r dammian-mask-frontend/dist/ ./backend/app/frontend_dist

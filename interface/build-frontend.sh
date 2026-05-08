(
  cd dammian-mask-frontend
  bun run build
)

cp dammian-mask-frontend/dist/ ./backend/app/frontend_dist -r

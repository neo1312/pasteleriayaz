#!/bin/bash
set -e

ENV="${1:-local}"
COMMIT_MSG="${2:-deploy}"

case $ENV in
    local)
        source venv/bin/activate
        python manage.py makemigrations
        python manage.py migrate
        python manage.py runserver
        ;;
    stage)
        echo "Starting staging deployment ..."
        COMPOSE="docker compose -f docker-compose.stage.yml --env-file .env.stage"
        echo "Building and starting containers..."
        $COMPOSE down
        $COMPOSE up --build -d --remove-orphans
        echo "Waiting for containers to come up..."
        echo "Current container status:"
        $COMPOSE ps
        echo "Stage deployment completed"
        ;;

    prod)
        echo "Starting production deployment..."
        git add .
        git commit -m "$COMMIT_MSG" --allow-empty
        git push
        ssh root@your-server-ip <<EOF
cd /app/pasteleriayaz
git pull
docker compose -f docker-compose.prod.yml --env-file .env.prod down
docker compose -f docker-compose.prod.yml --env-file .env.prod up --build -d --remove-orphans
EOF
        echo "Production deployment completed"
        ;;
    *)
        echo "Usage: $0 {local|stage|prod} [commit_message]"
        exit 1
        ;;
esac

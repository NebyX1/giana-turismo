$ErrorActionPreference = 'Stop'
Write-Warning 'ESTE SCRIPT BORRA TODO DOCKER DE TODA LA MÁQUINA.'
Write-Warning 'Se eliminarán contenedores, imágenes, volúmenes, redes de usuario y cachés de build de TODOS los proyectos.'
$confirmation = Read-Host 'Escribí BORRAR TODO DOCKER para continuar'
if ($confirmation -cne 'BORRAR TODO DOCKER') { throw 'Limpieza cancelada.' }
docker ps -aq | ForEach-Object { if ($_){ docker stop $_ } }
docker ps -aq | ForEach-Object { if ($_){ docker rm -f $_ } }
docker images -aq | Sort-Object -Unique | ForEach-Object { if ($_){ docker rmi -f $_ } }
docker volume ls -q | ForEach-Object { if ($_){ docker volume rm -f $_ } }
docker network ls --format '{{.Name}}' | Where-Object { $_ -notin @('bridge','host','none') } | ForEach-Object { docker network rm $_ }
docker builder prune -a -f
docker buildx prune -a -f
docker system prune -a --volumes -f
docker system df

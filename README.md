# Enfusion Map Builder

Модульная система создания полезных для gameplay игровых миров для Enfusion с перспективой поддержки Arma 4.

## Основное направление

Основное направление — детерминированные синтетические миры, создаваемые по seed, описанию и параметрам. Вторичный режим — реконструкция реальных территорий по DEM, GIS, OSM, ортофото и другим геоданным.

Высокоуровневый конвейер:

```text
World Description / Seed / Parameters
-> World Planner
-> Terrain Backend
-> WorldModel
-> Core (terrain processing, hydrology, biomes, roads, settlements,
         vegetation, Asset Resolver, validation)
-> Game Adapter (Arma Reforger, future Arma 4)
```

World Planner задаёт семантический замысел, ограничения и воспроизводимые параметры мира. Terrain Backend создаёт данные рельефа по этому плану. Им может быть зрелый внешний инструмент, научная или open-source система, RealWorld DEM либо минимальный тестовый backend. Независимо от источника результат приводится к общему WorldModel; Core/Terrain отвечает за backend-neutral обработку и проверку данных, а не за собственный production-grade синтез рельефа.

## Принцип разработки

Сначала найти существующее решение, затем сравнить, протестировать, интегрировать и расширить его. Собственный код пишется только при необходимости. Gaea сейчас является ведущим кандидатом на роль production terrain backend, но не обязательной или постоянной зависимостью архитектуры.

## Текущий статус

Проект находится на стадии архитектурной и интеграционной основы и оценки terrain backends. Разработка собственного production terrain engine сейчас не планируется. Конкретный runtime dependency stack будет определён после появления реального backend/integration кода.

Ruhnu — отдельный RealWorld production/test проект, а не архитектура генератора.

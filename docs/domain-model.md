# Domain Model

CellarMind distinguishes between a wine and a bottle.

This distinction is fundamental.

## Wine

A Wine represents a wine identity.

Example:

- Domaine de la Romanée Conti
- Romanée Conti Grand Cru
- 1962

There is only one Wine for this definition.

## Bottle

A Bottle represents one physical bottle.

Several bottles may refer to the same Wine.

Each bottle has its own:

- format
- location
- purchase information
- opening date
- tasting history
- status

## Cellar

A cellar is a physical storage place.

Examples:

- Home cellar
- Holiday house
- Professional storage

## Location

A precise place inside a cellar.

Examples:

- Rack A
- Shelf 3
- Bin 12

## DrinkWindow

Represents the estimated maturity window.

Contains:

- drink_from
- peak
- drink_until
- confidence
- evidences

## Evidence

Every enrichment must be explainable.

Evidence records:

- source
- confidence
- date
- comment

## Tasting

Represents one tasting event.

Belongs to a Bottle.

Never to a Wine.

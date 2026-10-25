/* eslint-disable no-undef */
// Copied from overleaf/overleaf bin/shared/mongodb-init-replica-set.js: Overleaf needs MongoDB as a replica set.

rs.initiate({ _id: 'overleaf', members: [{ _id: 0, host: 'mongo:27017' }] })

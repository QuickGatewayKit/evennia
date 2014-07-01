"""
Spawner

The spawner takes input files containing object definitions in
dictionary forms. These use a prototype architechture to define
unique objects without having to make a Typeclass for each.

The main function is spawn(*prototype), where the prototype
is a dictionary like this:

GOBLIN = {
 "typeclass": "game.gamesrc.objects.objects.Monster",
 "key": "goblin grunt",
 "health": lambda: randint(20,30),
 "resists": ["cold", "poison"],
 "attacks": ["fists"],
 "weaknesses": ["fire", "light"]
 }

Possible keywords are:
    prototype - dict, parent prototype of this structure (see below)
    key - string, the main object identifier
    typeclass - string, if not set, will use settings.BASE_OBJECT_TYPECLASS
    location - this should be a valid object or #dbref
    home - valid object or #dbref
    destination - only valid for exits (object or dbref)

    permissions - string or list of permission strings
    locks - a lock-string
    aliases - string or list of strings

    ndb_<name> - value of a nattribute (ndb_ is stripped)
    any other keywords are interpreted as Attributes and their values.

Each value can also be a callable that takes no arguments. It should
return the value to enter into the field and will be called every time
the prototype is used to spawn an object.

By specifying a prototype, the child will inherit all prototype slots
it does not explicitly define itself, while overloading those that it
does specify.

GOBLIN_WIZARD = {
 "prototype": GOBLIN,
 "key": "goblin wizard",
 "spells": ["fire ball", "lighting bolt"]
 }

GOBLIN_ARCHER = {
 "prototype": GOBLIN,
 "key": "goblin archer",
 "attacks": ["short bow"]
}

One can also have multiple prototypes. These are inherited from the
left, with the ones further to the right taking precedence.

ARCHWIZARD = {
 "attack": ["archwizard staff", "eye of doom"]

GOBLIN_ARCHWIZARD = {
 "key" : "goblin archwizard"
 "prototype": (GOBLIN_WIZARD, ARCHWIZARD),
}

The goblin archwizard will have some different attacks, but will
otherwise have the same spells as a goblin wizard who in turn shares
many traits with a normal goblin.

"""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.environ['DJANGO_SETTINGS_MODULE'] = 'game.settings'

from django.conf import settings
from random import randint
from src.objects.models import ObjectDB
from src.utils.create import handle_dbref

_CREATE_OBJECT_KWARGS = ("key", "location", "home", "destination")

_handle_dbref = lambda inp: handle_dbref(inp, ObjectDB)


def _get_prototype(dic, prot):
    "Recursively traverse a prototype dictionary, including multiple inheritance"
    if "prototype" in dic:
        # move backwards through the inheritance
        prototypes = dic["prototype"]
        if isinstance(prototypes, dict):
            prototypes = (prototypes,)
        for prototype in prototypes:
            # Build the prot dictionary in reverse order, overloading
            new_prot = _get_prototype(prototype, prot)
            prot.update(new_prot)
    prot.update(dic)
    prot.pop("prototype", None) # we don't need this anymore
    return prot


def _batch_create_object(*objparams):
    """
    This is a cut-down version of the create_object() function,
    optimized for speed. It does NOT check and convert various input
    so make sure the spawned Typeclass works before using this!

    Input:
    objsparams - each argument should be a tuple of arguments for the respective
                 creation/add handlers in the following order:
                    (create, permissions, locks, aliases, nattributes, attributes)
    Returns:
    A list of created objects
    """

    # bulk create all objects in one go
    dbobjs = [ObjectDB(**objparam[0]) for objparam in objparams]
    # unfortunately this doesn't work since bulk_create don't creates pks;
    # the result are double objects at the next stage
    #dbobjs = _ObjectDB.objects.bulk_create(dbobjs)

    objs = []
    for iobj, dbobj in enumerate(dbobjs):
        # call all setup hooks on each object
        objparam = objparams[iobj]
        obj = dbobj.typeclass # this saves dbobj if not done already
        obj.basetype_setup()
        obj.at_object_creation()

        if objparam[1]:
            # permissions
            obj.permissions.add(objparam[1])
        if objparam[2]:
            # locks
            obj.locks.add(objparam[2])
        if objparam[3]:
            # aliases
            obj.aliases.add(objparam[3])
        if objparam[4]:
            # nattributes
            for key, value in objparam[4].items():
                obj.nattributes.add(key, value)
        if objparam[5]:
            # attributes
            keys, values = objparam[5].keys(), objparam[5].values()
            obj.attributes.batch_add(keys, values)

        obj.basetype_posthook_setup()
        objs.append(obj)
    return objs


def spawn(*prototypes):
    """
    Spawn a number of prototyped objects. Each argument should be a
    prototype dictionary.
    """
    objsparams = []

    for prototype in prototypes:

        prot = _get_prototype(prototype, {})
        if not prot:
            continue

        # extract the keyword args we need to create the object itself
        create_kwargs = {}
        create_kwargs["db_key"] = prot.pop("key", "Spawned Object %06i" % randint(1,100000))
        create_kwargs["db_location"] = _handle_dbref(prot.pop("location", None))
        create_kwargs["db_home"] = _handle_dbref(prot.pop("home", settings.DEFAULT_HOME))
        create_kwargs["db_destination"] = _handle_dbref(prot.pop("destination", None))
        create_kwargs["db_typeclass_path"] = prot.pop("typeclass", settings.BASE_OBJECT_TYPECLASS)

        # extract calls to handlers
        permission_string = prot.pop("permissions", "")
        lock_string = prot.pop("locks", "")
        alias_string = prot.pop("aliases", "")

        # extract ndb assignments
        nattributes = dict((key.split("_", 1)[1], value if callable(value) else value)
                            for key, value in prot.items() if key.startswith("ndb_"))

        # the rest are attributes
        attributes = dict((key, value() if callable(value) else value)
                           for key, value in prot.items()
                           if not (key in _CREATE_OBJECT_KWARGS or key in nattributes))

        # pack for call into _batch_create_object
        objsparams.append( (create_kwargs, permission_string, lock_string,
                            alias_string, nattributes, attributes) )

    return _batch_create_object(*objsparams)


if __name__ == "__main__":
    # testing

    NOBODY = {}

    GOBLIN = {
     "key": "goblin grunt",
     "health": lambda: randint(20,30),
     "resists": ["cold", "poison"],
     "attacks": ["fists"],
     "weaknesses": ["fire", "light"]
     }

    GOBLIN_WIZARD = {
     "prototype": GOBLIN,
     "key": "goblin wizard",
     "spells": ["fire ball", "lighting bolt"]
     }

    GOBLIN_ARCHER = {
     "prototype": GOBLIN,
     "key": "goblin archer",
     "attacks": ["short bow"]
    }

    ARCHWIZARD = {
     "attacks": ["archwizard staff"],
    }

    GOBLIN_ARCHWIZARD = {
     "key": "goblin archwizard",
     "prototype" : (GOBLIN_WIZARD, ARCHWIZARD)
    }
    # test
    print [o.key for o in spawn(GOBLIN, GOBLIN_ARCHWIZARD)]
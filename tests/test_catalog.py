import unittest
from catalog import Catalog, BUILTIN, CUSTOM, ALL_MAPS, settings_profile
from counter import CounterSession


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.catalog = Catalog()

    def test_murky_swamp_rename_and_new_map_do_not_change_monster_exp(self):
        for name in ('The Murky Swamp I','The Murky Swamp II','the murky swamp'):
            self.assertEqual(self.catalog.profile(name),{self.catalog.labels[18]:39,self.catalog.labels[29]:58})
        self.assertIn('The Murky Swamp II',self.catalog.maps)
        self.assertNotIn('The Murky Swamp',self.catalog.maps)
        self.assertEqual(self.catalog.profile('Cabin of the Forsaken'),{'Shade':488})
        with self.assertRaises(ValueError):self.catalog.profile('The Murky Swamp III')

    def test_ant_tunnel_classifies_both_monsters(self):
        profile = self.catalog.profile('Ant Tunnel I')
        self.assertEqual(set(profile.values()), {41, 45})
        session = CounterSession(profile)
        for i, amount in enumerate((41, 45, 41)):
            session.accept(str(i), 'exp', amount, 'white')
        self.assertEqual(sum(session.counts.values()), 3)
        self.assertEqual(session.unresolved, 0)

    def test_launch_monsters_and_maps_have_exp_and_no_blank_map(self):
        self.assertNotIn('',self.catalog.maps)
        self.assertEqual(self.catalog.profile('Excavation Site I'),{'Ghost Stump':35,'Wooden Mask':43})
        self.assertEqual(self.catalog.profile('Excavation Site III'),{'Rocky Mask':45,'Wooden Mask':43})
        self.assertEqual(self.catalog.profile('Camp 1'),{'Skeleton Soldier':183,'Officer Skeleton':242})
        self.assertEqual(self.catalog.profile('Remains (Cliff)'),{'Commander Skeleton':390,'Officer Skeleton':242})
        self.assertIn(276,self.catalog.profile('Parched Land').values())
        self.assertEqual(set(self.catalog.profile('Parched Land').values()),{32,43,69,276})
        self.assertNotIn('Glowshroom',self.catalog.profile())
        self.assertNotIn('Orange Slime',self.catalog.profile())

    def test_dated_hunting_map_reference_is_covered(self):
        from scripts.audit_catalog import audit
        source,missing=audit(self.catalog)
        self.assertEqual(source['index_rows_checked'],132)
        self.assertEqual(missing,[])

    def test_shared_exp_requires_map_instead_of_arbitrary_monster(self):
        session=CounterSession(self.catalog.profile())
        row=session.accept('global','exp',35,'white')
        self.assertEqual(row['status'],'ambiguous_exp')
        self.assertEqual(sum(session.counts.values()),0)
        session=CounterSession(self.catalog.profile('Excavation Site I'))
        row=session.accept('local','exp',35,'white')
        self.assertEqual(row['monster'],'Ghost Stump')

    def test_duplicate_names_keep_distinct_variants(self):
        profile = self.catalog.profile()
        names = [name for name in profile if name.startswith('Blue Mushroom')]
        self.assertEqual(len(names), 2)
        self.assertEqual({profile[name] for name in names}, {35, 56})

    def test_identical_exp_is_ambiguous_on_special_map(self):
        profile = self.catalog.profile('Ant Tunnel For Bowman')
        self.assertGreaterEqual(sum(exp == 56 for exp in profile.values()), 2)
        session = CounterSession(profile)
        event = session.accept('1', 'exp', 56, 'white')
        self.assertEqual(event['status'], 'ambiguous_exp')
        self.assertEqual(sum(session.counts.values()), 0)

    def test_map_validation_prevents_silent_wrong_scope(self):
        self.assertEqual(self.catalog.profile(ALL_MAPS), self.catalog.profile())
        self.assertEqual(self.catalog.profile('ant tunnel i'), self.catalog.profile('Ant Tunnel I'))
        with self.assertRaises(ValueError):
            self.catalog.profile('Ant Tunnel')

    def test_unplaced_zero_exp_and_test_entries_excluded(self):
        self.assertTrue(all(m['exp'] > 0 and m['maps'] for m in self.catalog.records))
        self.assertFalse(any(m['name'].startswith('Test(') for m in self.catalog.records))

    def test_exp_multiplier_and_bad_inputs(self):
        self.assertEqual(set(self.catalog.profile('Ant Tunnel I', '1.5').values()), {61, 67})
        for value in ('0', '-1', 'NaN', 'Infinity', 'abc', '11'):
            with self.assertRaises(ValueError):
                self.catalog.profile(multiplier=value)

    def test_settings_replay_uses_same_profile_and_preserves_old_custom(self):
        config = dict(catalog_mode=BUILTIN, map='Ant Tunnel I', exp_multiplier='1', monsters='Wrong,999')
        self.assertEqual(settings_profile(config), self.catalog.profile('Ant Tunnel I'))
        self.assertEqual(settings_profile({'monsters':'Legacy,123'}), {'Legacy':123})
        config['catalog_mode'] = CUSTOM
        self.assertEqual(settings_profile(config), {'Wrong':999})


if __name__ == '__main__':
    unittest.main()

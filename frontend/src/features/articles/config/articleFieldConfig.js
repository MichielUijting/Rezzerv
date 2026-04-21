import { ARTICLE_TABS, ARTICLE_TYPES, FIELD_GROUPS } from './articleFieldConstants'

export const articleFieldConfig = [
  { key: 'article_name', tab: ARTICLE_TABS.OVERVIEW, group: FIELD_GROUPS.BASIC, label: 'Artikelnaam', visibilityType: 'always', applicableArticleTypes: [ARTICLE_TYPES.ALL], editable: true, order: 10 },
  { key: 'custom_name', tab: ARTICLE_TABS.OVERVIEW, group: FIELD_GROUPS.BASIC, label: 'Eigen naam', visibilityType: 'default_on', applicableArticleTypes: [ARTICLE_TYPES.ALL], editable: true, order: 20 },
  { key: 'article_type', tab: ARTICLE_TABS.OVERVIEW, group: FIELD_GROUPS.BASIC, label: 'Artikeltype', visibilityType: 'default_on', applicableArticleTypes: [ARTICLE_TYPES.ALL], editable: true, order: 30 },
  { key: 'category', tab: ARTICLE_TABS.OVERVIEW, group: FIELD_GROUPS.BASIC, label: 'Categorie', visibilityType: 'default_on', applicableArticleTypes: [ARTICLE_TYPES.ALL], editable: true, order: 40 },
  { key: 'brand_or_maker', tab: ARTICLE_TABS.OVERVIEW, group: FIELD_GROUPS.BASIC, label: 'Merk / maker / aanbieder', visibilityType: 'default_on', applicableArticleTypes: [ARTICLE_TYPES.ALL], editable: true, order: 50 },
  { key: 'source', tab: ARTICLE_TABS.OVERVIEW, group: FIELD_GROUPS.BASIC, label: 'Bron', visibilityType: 'default_off', applicableArticleTypes: [ARTICLE_TYPES.ALL], editable: false, order: 60 },
  { key: 'status', tab: ARTICLE_TABS.OVERVIEW, group: FIELD_GROUPS.BASIC, label: 'Status', visibilityType: 'default_on', applicableArticleTypes: [ARTICLE_TYPES.ALL], editable: true, order: 70 },
  { key: 'short_description', tab: ARTICLE_TABS.OVERVIEW, group: FIELD_GROUPS.BASIC, label: 'Korte omschrijving', visibilityType: 'default_on', applicableArticleTypes: [ARTICLE_TYPES.ALL], editable: true, order: 80 },

  { key: 'barcode', tab: ARTICLE_TABS.OVERVIEW, group: FIELD_GROUPS.EXTERNAL, label: 'Barcode', visibilityType: 'default_on', applicableArticleTypes: [ARTICLE_TYPES.ALL], editable: false, order: 110 },
  { key: 'variant', tab: ARTICLE_TABS.OVERVIEW, group: FIELD_GROUPS.EXTERNAL, label: 'Variant', visibilityType: 'default_off', applicableArticleTypes: [ARTICLE_TYPES.ALL], editable: true, order: 120 },
  { key: 'size_value', tab: ARTICLE_TABS.OVERVIEW, group: FIELD_GROUPS.EXTERNAL, label: 'Inhoud / omvang', visibilityType: 'default_on', applicableArticleTypes: [ARTICLE_TYPES.ALL], editable: true, order: 130 },
  { key: 'size_unit', tab: ARTICLE_TABS.OVERVIEW, group: FIELD_GROUPS.EXTERNAL, label: 'Eenheid', visibilityType: 'default_on', applicableArticleTypes: [ARTICLE_TYPES.ALL], editable: true, order: 140 },
  { key: 'purchase_date', tab: ARTICLE_TABS.OVERVIEW, group: FIELD_GROUPS.EXTERNAL, label: 'Aankoopdatum', visibilityType: 'default_on', applicableArticleTypes: [ARTICLE_TYPES.ALL], editable: true, order: 150 },

  { key: 'calories', tab: ARTICLE_TABS.OVERVIEW, group: FIELD_GROUPS.NUTRITION_PACKAGING, label: 'Calorieën', visibilityType: 'default_off', applicableArticleTypes: [ARTICLE_TYPES.ALL], editable: true, order: 210 },
  { key: 'fat_total', tab: ARTICLE_TABS.OVERVIEW, group: FIELD_GROUPS.NUTRITION_PACKAGING, label: 'Vetgehalte totaal', visibilityType: 'default_off', applicableArticleTypes: [ARTICLE_TYPES.ALL], editable: true, order: 220 },
  { key: 'emballage', tab: ARTICLE_TABS.OVERVIEW, group: FIELD_GROUPS.NUTRITION_PACKAGING, label: 'Emballage', visibilityType: 'default_off', applicableArticleTypes: [ARTICLE_TYPES.ALL], editable: true, order: 230 },
  { key: 'emballage_amount', tab: ARTICLE_TABS.OVERVIEW, group: FIELD_GROUPS.NUTRITION_PACKAGING, label: 'Emballagebedrag', visibilityType: 'default_off', applicableArticleTypes: [ARTICLE_TYPES.ALL], editable: true, order: 240 },

  { key: 'notes', tab: ARTICLE_TABS.OVERVIEW, group: FIELD_GROUPS.USER, label: 'Notities', visibilityType: 'default_on', applicableArticleTypes: [ARTICLE_TYPES.ALL], editable: true, order: 310 },
]

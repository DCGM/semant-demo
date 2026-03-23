<template>
  <q-page class="q-pt-sm">
    <div class="row">
      <q-btn unelevated icon="arrow_back" :to="{ name: 'collections' }" class="q-px-lg" >
        <q-tooltip>Back to Collections</q-tooltip>
      </q-btn>
      <q-separator vertical size="1.8px" inset />
      <q-tabs indicator-color="primary" active-class="active-tab text-primary" narrow-indicator inline-label style="flex:1" align="justify">
        <q-route-tab
          name="overview"
          label="Overview"
          icon="dashboard"
          :to="{ name: 'collectionOverview' }"
        />
        <q-separator vertical size="1.8px" inset />
        <q-route-tab
          name="documents"
          label="Documents"
          icon="library_books"
          :to="{ name: 'collectionDocuments' }"
        />
        <q-separator vertical size="1.8px" inset />
        <q-route-tab
          name="tags"
          label="Tags"
          icon="local_offer"
          :to="{ name: 'collectionTags' }"
        />
        <q-separator vertical size="1.8px" inset />
        <q-route-tab
          name="members"
          label="Members"
          icon="people"
          :to="{ name: 'collectionMembers' }"
        />
      </q-tabs>
    </div>
    <q-separator spaced="sm" size="1.7px" />
    <router-view />
  </q-page>
</template>

<style scoped lang="scss">
.active-tab {
  background-color: #e8f0fe;
  border-radius: 5px;
}
</style>

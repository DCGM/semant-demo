<template>
  <q-page class="column flex-center q-pa-lg text-center">
    <q-icon name="cloud_off" size="56px" color="grey-6" />
    <div class="text-h6 q-mt-md">Waiting to verify your session</div>
    <div class="text-body2 text-grey-8 q-mt-sm session-pending-text">
      This page needs your account. It opens as soon as the server confirms your session;
      you are not signed out.
    </div>
  </q-page>
</template>

<script setup lang="ts">
// A protected link waiting while the stored session cannot be verified (router/authGuard.ts).
// Retry and Sign out are in the layout's session banner.
</script>

<style scoped>
.session-pending-text {
  max-width: 420px;
}
</style>

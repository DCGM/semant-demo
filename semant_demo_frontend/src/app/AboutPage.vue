<template>
  <q-page class="about-page q-pa-md">
    <article class="about-content">
      <header class="row items-center no-wrap q-mb-md">
        <img :src="semantLogo" alt="semANT logo" class="about-logo q-mr-md" />
        <div>
          <h1 class="text-h5 q-my-none">About semANT demo</h1>
          <div class="text-subtitle2 text-grey-7">
            Semantic exploration of digitised Czech cultural-heritage texts
          </div>
        </div>
      </header>

      <p>
        semANT demo helps you find, read and organise passages in a large corpus of digitised
        historical documents. It combines full-text and meaning-based (vector) search with
        AI-generated summaries, answers to questions and suggestions for tagging text.
      </p>

      <h2 class="text-h6 q-mb-sm">What you can do</h2>
      <ul class="about-features">
        <li>
          <strong><router-link :to="{ name: 'search' }">Document search</router-link></strong>:
          find passages by words or by meaning, filter by metadata and tags, and get short summaries
          of the results.
        </li>
        <li>
          <strong><router-link :to="{ name: 'rag' }">Chat Assistant</router-link></strong>:
          ask questions and get answers drawn from the corpus, with citations of their sources.
        </li>
        <li>
          <strong>Collections</strong>: gather documents into your own collections and share them
          with other users (requires an account).
        </li>
        <li>
          <strong>Annotations</strong>: tag passages in a document by hand or review the tags the
          AI suggests, with its reasons.
        </li>
        <li>
          <strong><router-link :to="{ name: 'corpus' }">Corpus overview</router-link></strong>:
          see how many documents the corpus holds, by publication year, source library and language.
        </li>
      </ul>

      <h2 class="text-h6 q-mb-sm">The project</h2>
      <p>
        semANT demo is developed within the NAKI III programme project
        <strong>DH23P03OVV060</strong> by a consortium of
        <strong>Brno University of Technology</strong>, the <strong>Moravian Library</strong>
        and <strong>Masaryk University</strong>.
      </p>

      <h2 class="text-h6 q-mb-sm">More information</h2>
      <p>
        Technical details, documentation and source code are in the
        <a :href="readmeUrl" target="_blank" rel="noopener noreferrer">project README on GitHub</a>.
      </p>
    </article>
  </q-page>
</template>

<script setup lang="ts">
import semantLogo from 'src/assets/semant-logo.png'

const readmeUrl = 'https://github.com/DCGM/semant-demo#readme'
</script>

<style scoped>
.about-content {
  max-width: 760px;
  margin: 0 auto;
  overflow-wrap: anywhere;
}

.about-logo {
  height: 56px;
  width: auto;
  flex-shrink: 0;
}

.about-features {
  padding-left: 1.25rem;
}

.about-features li {
  margin-bottom: 0.5rem;
}
</style>

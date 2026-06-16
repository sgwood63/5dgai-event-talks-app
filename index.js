#!/usr/bin/env node

import Parser from 'rss-parser';
import prompts from 'prompts';
import pc from 'picocolors';
import open from 'open';

const parser = new Parser();

// Base URL for Google News RSS
const BASE_FEED_URL = 'https://news.google.com/rss';
const BASE_TOPIC_URL = 'https://news.google.com/news/rss/headlines/section/topic';

const CATEGORIES = [
  { title: '🌍 Top Stories', value: { type: 'top' } },
  { title: '🏳️  World News', value: { type: 'topic', id: 'WORLD' } },
  { title: '🇺🇸 US News', value: { type: 'topic', id: 'NATION' } },
  { title: '💼 Business', value: { type: 'topic', id: 'BUSINESS' } },
  { title: '💻 Technology', value: { type: 'topic', id: 'TECHNOLOGY' } },
  { title: '🎬 Entertainment', value: { type: 'topic', id: 'ENTERTAINMENT' } },
  { title: '⚽ Sports', value: { type: 'topic', id: 'SPORTS' } },
  { title: '🧪 Science', value: { type: 'topic', id: 'SCIENCE' } },
  { title: '🏥 Health', value: { type: 'topic', id: 'HEALTH' } },
  { title: '🔍 Search News...', value: { type: 'search' } },
  { title: '🚪 Exit', value: { type: 'exit' } }
];

// Wrap prompts to handle Ctrl+C cleanly
async function ask(questions) {
  const response = await prompts(questions, {
    onCancel: () => {
      console.log(pc.yellow('\nGoodbye!'));
      process.exit(0);
    }
  });
  return response;
}

// Clear the screen and show banner
function showHeader(subtitle = '') {
  console.clear();
  console.log(pc.bold(pc.cyan('╔══════════════════════════════════════════════════════════╗')));
  console.log(pc.bold(pc.cyan('║                    GOOGLE NEWS CLI                       ║')));
  console.log(pc.bold(pc.cyan('╚══════════════════════════════════════════════════════════╝')));
  if (subtitle) {
    console.log(pc.italic(pc.gray(` > ${subtitle}`)));
  }
  console.log();
}

// Format the feed URL based on user selection
function getFeedUrl(selection, searchQuery = '') {
  const params = '?hl=en-US&gl=US&ceid=US:en';
  if (selection.type === 'top') {
    return `${BASE_FEED_URL}${params}`;
  } else if (selection.type === 'topic') {
    return `${BASE_TOPIC_URL}/${selection.id}${params}`;
  } else if (selection.type === 'search') {
    return `${BASE_FEED_URL}/search?q=${encodeURIComponent(searchQuery)}&hl=en-US&gl=US&ceid=US:en`;
  }
  return null;
}

// Clean and split title into Headline and Source
function parseTitle(title) {
  // Google News titles format is typically: "Headline - Source Name"
  const parts = title.split(' - ');
  if (parts.length > 1) {
    const source = parts.pop();
    const headline = parts.join(' - ');
    return { headline, source };
  }
  return { headline: title, source: 'Google News' };
}

async function main() {
  while (true) {
    showHeader('Stay updated right from your terminal');

    const { menuChoice } = await ask({
      type: 'select',
      name: 'menuChoice',
      message: 'Choose a news category:',
      choices: CATEGORIES,
      initial: 0
    });

    if (menuChoice.type === 'exit') {
      console.log(pc.green('Goodbye! Thanks for using Google News CLI.'));
      break;
    }

    let searchQuery = '';
    if (menuChoice.type === 'search') {
      const searchResponse = await ask({
        type: 'text',
        name: 'query',
        message: 'Enter search keywords:'
      });
      searchQuery = searchResponse.query.trim();
      if (!searchQuery) {
        console.log(pc.red('Search query cannot be empty! Press any key to continue...'));
        await ask({ type: 'text', name: 'any', message: 'Press Enter to return to menu' });
        continue;
      }
    }

    // Fetch and parse the feed
    showHeader(menuChoice.type === 'search' ? `Searching for "${searchQuery}"...` : `Fetching latest stories...`);
    
    const url = getFeedUrl(menuChoice, searchQuery);
    
    try {
      const feed = await parser.parseURL(url);
      
      if (!feed.items || feed.items.length === 0) {
        console.log(pc.yellow('No articles found. Press Enter to return to menu...'));
        await ask({ type: 'text', name: 'any', message: '' });
        continue;
      }

      await browseArticles(feed.items, menuChoice, searchQuery);
    } catch (err) {
      console.log(pc.red(`\nError fetching news: ${err.message}`));
      console.log(pc.gray('Please check your internet connection and try again.'));
      await ask({ type: 'text', name: 'any', message: 'Press Enter to return to main menu' });
    }
  }
}

async function browseArticles(items, categoryChoice, searchQuery) {
  let initialIndex = 0;

  while (true) {
    showHeader(categoryChoice.type === 'search' ? `Results for "${searchQuery}"` : `Latest Stories`);

    const choices = [
      { title: pc.bold(pc.yellow('⬅  Back to Main Menu')), value: 'back' },
      ...items.map((item, index) => {
        const { headline, source } = parseTitle(item.title);
        return {
          title: `${pc.cyan((index + 1).toString().padStart(2, ' '))}  ${headline} ${pc.dim(`(${source})`)}`,
          value: index
        };
      })
    ];

    const { articleChoice } = await ask({
      type: 'select',
      name: 'articleChoice',
      message: 'Select an article to read details:',
      choices: choices,
      initial: initialIndex,
      maxPerPage: 15
    });

    if (articleChoice === 'back') {
      break;
    }

    // Save the index to return back to the same spot in the list
    initialIndex = articleChoice + 1; // +1 because index 0 is 'Back to Main Menu'

    const article = items[articleChoice];
    await showArticleDetails(article);
  }
}

async function showArticleDetails(article) {
  const { headline, source } = parseTitle(article.title);
  const pubDate = article.pubDate ? new Date(article.pubDate).toLocaleString() : 'N/A';

  while (true) {
    showHeader('Article Details');

    console.log(pc.bold(pc.white(headline)));
    console.log(pc.cyan(`Source: `) + pc.green(source));
    console.log(pc.cyan(`Published: `) + pc.yellow(pubDate));
    console.log(pc.cyan(`Link: `) + pc.underline(pc.blue(article.link)));
    console.log();

    if (article.contentSnippet || article.content) {
      console.log(pc.bold(pc.white('Snippet:')));
      // Strip html tags just in case
      const snippet = (article.contentSnippet || article.content)
        .replace(/<\/?[^>]+(>|$)/g, "")
        .trim();
      console.log(pc.gray(snippet));
      console.log();
    }

    const { action } = await ask({
      type: 'select',
      name: 'action',
      message: 'Choose action:',
      choices: [
        { title: '🌐 Open full article in browser', value: 'open' },
        { title: '⬅  Back to articles list', value: 'back' }
      ]
    });

    if (action === 'open') {
      console.log(pc.green('Opening in browser...'));
      try {
        await open(article.link);
      } catch (err) {
        console.log(pc.red(`Failed to open link: ${err.message}`));
        await ask({ type: 'text', name: 'any', message: 'Press Enter to continue' });
      }
    } else {
      break;
    }
  }
}

main();

/**
 * The three questions the site answers and the stories under each. A story with `ready: false` is listed (so the
 * shape of the site is clear) but not linked until its page exists.
 */
export type Story = { slug: string; title: string; question: string; ready: boolean };
export type Section = { href: string; label: string; question: string; intro: string; stories: Story[] };

export const SECTIONS: Section[] = [
  {
    href: "/causes",
    label: "Causes",
    question: "Why is it happening?",
    intro: "What people burn, farm and clear, which gases that puts in the air, and how those gases trap heat.",
    stories: [
      { slug: "greenhouse-gases", title: "Greenhouse gases", question: "What is in the air, and how do we know it is us?", ready: false },
      { slug: "emissions", title: "Emissions", question: "Who emits, from what, and how much over time?", ready: false },
      { slug: "energy", title: "Energy", question: "Where does our energy come from, and how fast is that changing?", ready: false },
      { slug: "food-and-land", title: "Food and land", question: "How do farming and forests add to the problem?", ready: false },
    ],
  },
  {
    href: "/consequences",
    label: "Consequences",
    question: "What is it doing?",
    intro: "How much the planet has warmed, what that is doing to oceans and ice, to people, and to nature.",
    stories: [
      { slug: "temperature", title: "Temperature", question: "How much warmer is it, and do the measurements agree?", ready: false },
      { slug: "oceans-and-ice", title: "Oceans and ice", question: "Why is the sea rising, and how fast is the ice going?", ready: false },
      { slug: "people-and-extremes", title: "People and extremes", question: "Who is being hurt by heat, fire and floods?", ready: false },
      { slug: "nature", title: "Nature", question: "What is happening to wildlife and ecosystems?", ready: false },
    ],
  },
  {
    href: "/action",
    label: "What can be done",
    question: "What can be done?",
    intro: "Where current policies lead, which choices make the biggest difference, and what has worked.",
    stories: [
      { slug: "where-we-are-heading", title: "Where we are heading", question: "How much warming do today's policies and pledges lead to?", ready: false },
      { slug: "your-levers", title: "Your levers", question: "Where do I stand, and which choices change the most?", ready: false },
      { slug: "what-works", title: "What works", question: "Which policies have actually cut emissions?", ready: false },
    ],
  },
];
